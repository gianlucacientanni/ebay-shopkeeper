# standard library
import json
import tempfile
import unittest
from pathlib import Path
from unittest import TestCase, mock

# ebay_shopkeeper imports
from back_end.pal import review_call


PAL_OUTPUT = {
    "commander": "Radagast the Brown",
    "relaxed": False,
    "cards": [
        {"name": "Springleaf Drum", "price": "£1.99", "type": "Artifact", "text": "..."},
        {"name": "Troop of Ponies", "price": "£3.99", "type": "Creature — Horse", "text": "..."},
    ],
}
TRANSCRIPT = [
    {"role": "system", "content": "You are Tom..."},
    {"role": "assistant", "content": "Welcome to Arcanum Collectibles! What commander?",
     "seconds_from_start": 2.0, "duration": 3.0},
    {"role": "user", "content": "Radagast the Brown.", "seconds_from_start": 6.0, "duration": 1.5},
    {"role": "assistant", "content": "Nice! What's going wrong with it?",
     "seconds_from_start": 8.0, "duration": 2.0},
    {"role": "user", "content": "It's too slow.", "seconds_from_start": 11.0, "duration": 1.0},
    {"role": "assistant", "content": "Let me have a look at what's on the shelves…",
     "seconds_from_start": 13.0, "duration": 2.0,
     "tool_calls": [{"function": {"name": "search_cards",
                                  "arguments": '{"commander": "Radagast the Brown", "role": "ramp"}'}}]},
    {"role": "tool", "content": json.dumps(PAL_OUTPUT), "seconds_from_start": 15.0},
    {"role": "assistant", "content": "Grab Springleaf Drum for £1.99, it ramps you on turn two.",
     "seconds_from_start": 17.5, "duration": 4.0},
]
CONVERSATION = {
    "conversation_id": "c123",
    "status": "ended",
    "created_at": "2026-11-16T10:00:00Z",
    "events": [
        {"event_type": "system.pal_joined", "properties": {}},
        {"event_type": "application.transcription_ready", "properties": {"transcript": TRANSCRIPT}},
        {"event_type": "system.shutdown", "properties": {"shutdown_reason": "end_call"}},
    ],
}


def checks_by_name(result: dict) -> dict:
    return {name: (passed, detail) for name, passed, detail in result["checks"]}


class ReviewCallTest(TestCase):
    def test_review_successful_call(self):
        result = review_call.review(CONVERSATION)
        self.assertEqual(result["search_calls"], [{"commander": "Radagast the Brown", "role": "ramp"}])
        self.assertEqual(result["recommended"], ["Springleaf Drum"])
        self.assertEqual(result["time_to_recommendation"], 15.5)
        self.assertEqual(result["speaking_seconds"], 21.5)
        self.assertEqual(result["shutdown_reason"], "end_call")
        for name, (passed, detail) in checks_by_name(result).items():
            self.assertTrue(passed, f"Test case {name} failed: {detail}")

    def test_review_failures(self):
        test_cases = [
            {
                "description": "no transcript yet",
                "conversation": {"events": []},
                "failed_check": "Transcript available",
            },
            {
                "description": "search returned an error",
                "conversation": {"events": [{
                    "event_type": "application.transcription_ready",
                    "properties": {"transcript": [
                        {"role": "tool", "content": "The stock search failed: Scryfall returned 503"},
                    ]},
                }]},
                "failed_check": "Search returned cards",
            },
            {
                "description": "several questions in one turn",
                "conversation": {"events": [{
                    "event_type": "application.transcription_ready",
                    "properties": {"transcript": [
                        {"role": "assistant", "content": "What commander? And what's wrong?"},
                    ]},
                }]},
                "failed_check": "One question at a time",
            },
            {
                "description": "hit the time limit",
                "conversation": {**CONVERSATION, "events": CONVERSATION["events"][:2] + [
                    {"event_type": "system.shutdown",
                     "properties": {"shutdown_reason": "max_call_duration reached"}},
                ]},
                "failed_check": "Ended before the time limit",
            },
            {
                "description": "recommended a card that wasn't in the results",
                "conversation": {**CONVERSATION, "events": [
                    {"event_type": "application.transcription_ready", "properties": {"transcript":
                        TRANSCRIPT[:-1] + [{"role": "assistant", "content": "Get a Sol Ring."}]}},
                ]},
                "failed_check": "Tom recommended a card from the results",
            },
        ]
        for test_case in test_cases:
            test_desc = test_case["description"]
            checks = checks_by_name(review_call.review(test_case["conversation"]))
            self.assertFalse(checks[test_case["failed_check"]][0], f"Test case {test_desc} failed.")

    def test_tool_results_parse_json_and_keep_errors(self):
        turns = [
            {"role": "tool", "content": json.dumps(PAL_OUTPUT)},
            {"role": "tool", "content": "The stock search failed"},
            {"role": "assistant", "content": "{}"},
        ]
        self.assertEqual(review_call.tool_results(turns), [PAL_OUTPUT, "The stock search failed"])

    def test_mentioned_cards(self):
        test_cases = [
            {"description": "exact", "text": "Get Springleaf Drum.", "expected": ["Springleaf Drum"]},
            {"description": "case and punctuation", "text": "springleaf-drum!", "expected": ["Springleaf Drum"]},
            {"description": "none", "text": "Let me look.", "expected": []},
        ]
        for test_case in test_cases:
            test_desc = test_case["description"]
            self.assertEqual(
                review_call.mentioned_cards(test_case["text"], ["Springleaf Drum", "Troop of Ponies"]),
                test_case["expected"],
                f"Test case {test_desc} failed.",
            )

    def test_fetch_with_transcript_retries_until_ready(self):
        no_transcript = {"events": []}
        sleep = mock.Mock()
        with mock.patch.object(
            review_call.tavus, "get_conversation", side_effect=[no_transcript, no_transcript, CONVERSATION]
        ) as get_conversation:
            conversation = review_call.fetch_with_transcript(mock.Mock(), "c123", attempts=5, delay=1, sleep=sleep)
        self.assertEqual(conversation, CONVERSATION)
        self.assertEqual(get_conversation.call_count, 3)
        self.assertEqual(sleep.call_count, 2)

    def test_fetch_with_transcript_gives_up(self):
        sleep = mock.Mock()
        with mock.patch.object(review_call.tavus, "get_conversation", return_value={"events": []}):
            conversation = review_call.fetch_with_transcript(mock.Mock(), "c123", attempts=3, delay=1, sleep=sleep)
        self.assertEqual(conversation, {"events": []})
        self.assertEqual(sleep.call_count, 2)

    def test_render_and_write_markdown(self):
        result = review_call.review(CONVERSATION)
        markdown = review_call.render_markdown("c123", CONVERSATION, result)
        self.assertIn("# Call review: c123", markdown)
        self.assertIn("✔ Tom recommended a card from the results: Springleaf Drum", markdown)
        self.assertIn("**user**: Radagast the Brown.", markdown)
        self.assertIn("Shutdown reason: end_call", markdown)
        with tempfile.TemporaryDirectory() as tmp:
            path = review_call.write_review("c123", markdown, Path(tmp))
            self.assertTrue(path.name.endswith("-c123.md"))
            self.assertEqual(path.read_text(), markdown)


if __name__ == "__main__":
    unittest.main()
