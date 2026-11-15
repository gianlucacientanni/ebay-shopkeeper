# standard library
import json
import tempfile
import unittest
from pathlib import Path
from unittest import TestCase, mock

# ebay_shopkeeper imports
from back_end.api.tavus.tavus import TavusError
from back_end.pal import setup as pal_setup
from back_end.pal import shopkeeper


SAVED_STATE = {"tool_id": "t1", "objectives_id": "o1", "pal_id": "p1"}
TAVUS = "back_end.pal.setup.tavus"


def mock_tavus() -> mock.Mock:
    """
    A stand-in for the tavus module: gets succeed, creates return new ids.
    """
    fake = mock.Mock()
    fake.TavusError = TavusError
    fake.create_tool.return_value = "t-new"
    fake.create_objectives.return_value = "o-new"
    fake.create_pal.return_value = "p-new"
    return fake


def not_found(*args):
    raise TavusError("not found", status_code=404)


class SetupTest(TestCase):
    def test_setup_first_run_creates_everything(self):
        fake = mock_tavus()
        with mock.patch(TAVUS, fake):
            state = pal_setup.setup(mock.Mock(), {})

        self.assertEqual(state, {"tool_id": "t-new", "objectives_id": "o-new", "pal_id": "p-new"})
        fake.create_tool.assert_called_once_with(mock.ANY, shopkeeper.tool_definition())
        fake.create_objectives.assert_called_once_with(mock.ANY, shopkeeper.OBJECTIVES)
        fake.create_pal.assert_called_once_with(mock.ANY, shopkeeper.pal_definition("o-new"))
        fake.attach_tools.assert_called_once_with(mock.ANY, "p-new", ["t-new", "end_call"])
        fake.get_tool.assert_not_called()

    def test_setup_rerun_updates_instead_of_creating(self):
        fake = mock_tavus()
        with mock.patch(TAVUS, fake):
            state = pal_setup.setup(mock.Mock(), SAVED_STATE)

        self.assertEqual(state, SAVED_STATE)
        fake.update_tool.assert_called_once_with(mock.ANY, "t1", shopkeeper.tool_definition())
        fake.patch_objectives.assert_called_once_with(
            mock.ANY, "o1", shopkeeper.objectives_patch()
        )
        fake.patch_pal.assert_called_once_with(mock.ANY, "p1", shopkeeper.pal_patch("o1"))
        fake.create_tool.assert_not_called()
        fake.create_objectives.assert_not_called()
        fake.create_pal.assert_not_called()
        fake.attach_tools.assert_called_once_with(mock.ANY, "p1", ["t1", "end_call"])

    def test_setup_recreates_deleted_resources(self):
        test_cases = [
            {"description": "tool deleted", "get": "get_tool", "expected_key": "tool_id"},
            {
                "description": "objectives deleted",
                "get": "get_objectives",
                "expected_key": "objectives_id",
            },
            {"description": "PAL deleted", "get": "get_pal", "expected_key": "pal_id"},
        ]
        for test_case in test_cases:
            test_desc = test_case["description"]
            fake = mock_tavus()
            getattr(fake, test_case["get"]).side_effect = not_found
            with mock.patch(TAVUS, fake):
                state = pal_setup.setup(mock.Mock(), SAVED_STATE)
            key = test_case["expected_key"]
            self.assertTrue(state[key].endswith("-new"), f"Test case {test_desc} failed.")
            for other_key in set(SAVED_STATE) - {key} - {"pal_id"}:
                self.assertEqual(state[other_key], SAVED_STATE[other_key], f"Test case {test_desc} failed.")

    def test_setup_objectives_patch_rejected_creates_new_and_repoints_pal(self):
        fake = mock_tavus()
        fake.patch_objectives.side_effect = TavusError("bad patch", status_code=422)
        with mock.patch(TAVUS, fake):
            state = pal_setup.setup(mock.Mock(), SAVED_STATE)

        self.assertEqual(state["objectives_id"], "o-new")
        fake.patch_pal.assert_called_once_with(mock.ANY, "p1", shopkeeper.pal_patch("o-new"))

    def test_setup_unexpected_error_stops(self):
        fake = mock_tavus()
        fake.get_tool.side_effect = TavusError("server error", status_code=500)
        with mock.patch(TAVUS, fake), self.assertRaises(TavusError):
            pal_setup.setup(mock.Mock(), SAVED_STATE)
        fake.create_tool.assert_not_called()

    def test_main_dry_run_makes_no_calls(self):
        fake = mock_tavus()
        with (
            mock.patch(TAVUS, fake),
            mock.patch.object(pal_setup, "load_state", return_value={}),
            mock.patch("builtins.print") as printed,
        ):
            exit_code = pal_setup.main(["--dry-run"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(fake.mock_calls, [])
        payloads = json.loads(printed.call_args.args[0])
        self.assertEqual(set(payloads), {"tool", "objectives", "pal", "attach_tools"})

    def test_save_and_load_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "resources.json"
            self.assertEqual(pal_setup.load_state(path), {})
            pal_setup.save_state(SAVED_STATE, path)
            self.assertEqual(pal_setup.load_state(path), SAVED_STATE)


if __name__ == "__main__":
    unittest.main()
