# standard library
import unittest
from typing import get_args
from unittest import TestCase

# ebay_shopkeeper imports
from back_end.common.models import CardType, SearchRequest
from back_end.pal.shopkeeper import (
    FACE_ID,
    FALLBACK_OBJECTIVE,
    LLM_MODEL,
    OBJECTIVES,
    PROBLEM_BRANCHES,
    SYSTEM_PROMPT,
    TOOL_NAME,
    objectives_patch,
    pal_definition,
    pal_patch,
    tool_definition,
    tool_parameters,
)
from back_end.search.query import ROLE_FILTERS


# Tavus works best with prompts under about 5,000 tokens (roughly 4 characters per token).
PROMPT_CHAR_BUDGET = 20_000


class ShopkeeperTest(TestCase):
    def test_tool_parameters_match_search_request(self):
        parameters = tool_parameters()
        self.assertLessEqual(set(parameters["properties"]), set(SearchRequest.model_fields))
        self.assertEqual(parameters["required"], ["commander"])

    def test_tool_parameters_enums_match_backend(self):
        properties = tool_parameters()["properties"]
        self.assertEqual(properties["card_type"]["enum"], list(get_args(CardType)))
        self.assertEqual(properties["role"]["enum"], list(ROLE_FILTERS))

    def test_tool_parameters_accepted_by_search_request(self):
        properties = tool_parameters()["properties"]
        for role in properties["role"]["enum"]:
            for card_type in properties["card_type"]["enum"]:
                SearchRequest(commander="x", role=role, card_type=card_type, max_price=5)

    def test_tool_definition(self):
        tool = tool_definition()
        self.assertEqual(tool["name"], TOOL_NAME)
        self.assertEqual(tool["delivery"], {"app_message": True})
        self.assertEqual(tool["on_call"], "static_filler")
        self.assertTrue(tool["static_filler"])
        self.assertEqual(tool["on_resolve"], "generate_response")

    def test_objectives_chain(self):
        names = [objective["objective_name"] for objective in OBJECTIVES]
        self.assertEqual(len(names), len(set(names)))
        for objective in OBJECTIVES:
            name = objective["objective_name"]
            self.assertNotIn(" ", name, f"Test case {name} failed.")
            self.assertFalse(
                "next_required_objective" in objective
                and "next_conditional_objectives" in objective,
                f"Test case {name} failed.",
            )
            targets = list(objective.get("next_conditional_objectives", {}))
            if "next_required_objective" in objective:
                targets.append(objective["next_required_objective"])
            for target in targets:
                self.assertIn(target, names, f"Test case {name} -> {target} failed.")

    def test_objectives_all_reachable_from_first(self):
        by_name = {objective["objective_name"]: objective for objective in OBJECTIVES}
        reached, to_visit = set(), [OBJECTIVES[0]["objective_name"]]
        while to_visit:
            name = to_visit.pop()
            if name in reached:
                continue
            reached.add(name)
            objective = by_name[name]
            to_visit.extend(objective.get("next_conditional_objectives", {}))
            if "next_required_objective" in objective:
                to_visit.append(objective["next_required_objective"])
        self.assertEqual(reached, set(by_name))

    def test_objectives_start_with_commander_then_problem(self):
        self.assertEqual(
            [objective["objective_name"] for objective in OBJECTIVES[:2]],
            ["identify_commander", "identify_deck_problem"],
        )

    def test_problem_branches(self):
        problem = next(o for o in OBJECTIVES if o["objective_name"] == "identify_deck_problem")
        branch_names = [branch["objective_name"] for branch in PROBLEM_BRANCHES]
        self.assertEqual(
            list(problem["next_conditional_objectives"]), branch_names + [FALLBACK_OBJECTIVE]
        )
        by_name = {objective["objective_name"]: objective for objective in OBJECTIVES}
        for branch in PROBLEM_BRANCHES:
            name = branch["objective_name"]
            self.assertIn(branch["role"], ROLE_FILTERS, f"Test case {name} failed.")
            recommend = by_name[name]
            self.assertIn(f'role "{branch["role"]}"', recommend["objective_prompt"])
            self.assertIn("single best card", recommend["objective_prompt"])
            self.assertEqual(recommend["next_required_objective"], "wrap_up")

    def test_problem_branches_fallbacks(self):
        by_name = {objective["objective_name"]: objective for objective in OBJECTIVES}
        for branch in PROBLEM_BRANCHES:
            name = branch["objective_name"]
            self.assertIn(branch["fallback_role"], ROLE_FILTERS, f"Test case {name} failed.")
            self.assertNotEqual(branch["fallback_role"], branch["role"], f"Test case {name} failed.")
            prompt = by_name[name]["objective_prompt"]
            self.assertIn(f'role "{branch["fallback_role"]}"', prompt, f"Test case {name} failed.")
            self.assertIn("search once more", prompt, f"Test case {name} failed.")
        self.assertIn("search once more", by_name[FALLBACK_OBJECTIVE]["objective_prompt"])

    def test_problem_branches_examples(self):
        test_cases = [
            {"description": "deck too slow", "branch": "recommend_ramp", "role": "ramp"},
            {
                "description": "win condition foiled",
                "branch": "recommend_interaction",
                "role": "protection",
            },
        ]
        fallbacks = {branch["objective_name"]: branch["fallback_role"] for branch in PROBLEM_BRANCHES}
        self.assertEqual(fallbacks["recommend_interaction"], "removal")
        roles = {branch["objective_name"]: branch["role"] for branch in PROBLEM_BRANCHES}
        for test_case in test_cases:
            test_desc = test_case["description"]
            self.assertEqual(
                roles[test_case["branch"]], test_case["role"], f"Test case {test_desc} failed."
            )

    def test_objectives_patch_replaces_all_objectives(self):
        self.assertEqual(objectives_patch(), [{"op": "replace", "path": "/data", "value": OBJECTIVES}])

    def test_pal_definition(self):
        pal = pal_definition("o123")
        self.assertEqual(pal["default_face_id"], FACE_ID)
        self.assertEqual(pal["objectives_id"], "o123")
        self.assertEqual(pal["layers"]["llm"]["model"], LLM_MODEL)
        self.assertEqual(pal["layers"]["conversational_flow"]["turn_detection_model"], "sparrow-2")
        self.assertEqual(pal["pipeline_mode"], "full")
        self.assertEqual(pal["system_prompt"], SYSTEM_PROMPT)

    def test_pal_patch_matches_pal_definition(self):
        pal = pal_definition("o123")
        for operation in pal_patch("o123"):
            node = pal
            for key in operation["path"].strip("/").split("/"):
                node = node[key]
            self.assertEqual(operation["op"], "add", f"Test case {operation['path']} failed.")
            self.assertEqual(node, operation["value"], f"Test case {operation['path']} failed.")

    def test_system_prompt_within_budget(self):
        self.assertLess(len(SYSTEM_PROMPT), PROMPT_CHAR_BUDGET)
        self.assertIn(TOOL_NAME, SYSTEM_PROMPT)
        self.assertIn("single best card", SYSTEM_PROMPT)
        self.assertIn("search once more", SYSTEM_PROMPT)
        self.assertIn("Never search more than twice", SYSTEM_PROMPT)


if __name__ == "__main__":
    unittest.main()
