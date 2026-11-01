"""Offline tests for the decision inbox levels. Run: python -I -m unittest discover -s tests"""
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import decisions  # noqa: E402


def run_cli(home: str, *argv: str) -> str:
    out = io.StringIO()
    with mock.patch.object(sys, "argv", ["decisions.py", "--home", home, *argv]), \
            mock.patch.object(sys, "stdout", out), mock.patch.object(out, "reconfigure", create=True):
        decisions.main()
    return out.getvalue()


class LevelTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = self._tmp.name

    def test_old_store_without_level_loads_as_ego(self) -> None:
        os.makedirs(os.path.dirname(decisions.store_path(self.home)))
        with open(decisions.store_path(self.home), "w", encoding="utf-8") as fh:
            json.dump({"next": 2, "items": [{"id": "D-1", "kind": "manual", "title": "old", "status": "open"}]}, fh)
        self.assertEqual(decisions.load(self.home)["items"][0]["level"], "ego")

    def test_new_item_defaults_to_ego_and_rejects_unknown_level(self) -> None:
        data = {"next": 1, "items": []}
        self.assertEqual(decisions.new_item(data, "manual", "a")["level"], "ego")
        self.assertEqual(decisions.new_item(data, "manual", "b", level="id")["level"], "id")
        with self.assertRaises(ValueError):
            decisions.new_item(data, "manual", "c", level="nope")

    def test_add_level_flag_and_list_filter(self) -> None:
        run_cli(self.home, "add", "company thing")
        run_cli(self.home, "add", "harness thing", "--level", "superego")
        levels = {i["title"]: i["level"] for i in decisions.load(self.home)["items"]}
        self.assertEqual(levels, {"company thing": "ego", "harness thing": "superego"})
        listing = run_cli(self.home, "list", "--level", "superego")
        self.assertIn("harness thing", listing)
        self.assertNotIn("company thing", listing)

    def test_export_keeps_only_one_level_and_next(self) -> None:
        for title, level in (("a", "ego"), ("b", "id"), ("c", "ego")):
            run_cli(self.home, "add", title, "--level", level)
        store = json.loads(run_cli(self.home, "export", "--level", "ego"))
        self.assertEqual(store["next"], 4)
        self.assertEqual([i["title"] for i in store["items"]], ["a", "c"])

    def test_import_adds_new_ids_newer_wins_and_next_is_max(self) -> None:
        run_cli(self.home, "add", "mine")  # D-1
        run_cli(self.home, "add", "other")  # D-2
        data = decisions.load(self.home)
        data["items"][0]["created"] = "2026-01-01"
        decisions.save(data, self.home)
        newer = json.loads(json.dumps(data["items"][0]))
        newer.update(status="resolved", answer="A", resolved="2026-02-01")
        stale = json.loads(json.dumps(data["items"][1]))
        stale.update(title="stale edit", created="2025-01-01")
        extra = {"id": "D-9", "kind": "manual", "title": "new", "level": "superego", "status": "open", "created": "2026-03-01"}
        path = os.path.join(self.home, "in.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump({"next": 10, "items": [newer, stale, extra]}, fh)
        self.assertEqual(run_cli(self.home, "import", path).strip(), "import: 1 added, 1 updated, 1 unchanged")
        merged = decisions.load(self.home)
        by_id = {i["id"]: i for i in merged["items"]}
        self.assertEqual(by_id["D-1"]["status"], "resolved")
        self.assertEqual(by_id["D-2"]["title"], "other")
        self.assertIn("D-9", by_id)
        self.assertEqual(merged["next"], 10)

    def test_html_hides_id_details(self) -> None:
        data = {"next": 1, "items": []}
        decisions.new_item(data, "manual", "company visible", level="ego")
        decisions.new_item(data, "manual", "secret therapy topic", detail="very private", source="diary", level="id")
        page = decisions.render_html(data)
        self.assertIn("company visible", page)
        self.assertNotIn("secret therapy topic", page)
        self.assertNotIn("very private", page)
        self.assertNotIn("diary", page)
        self.assertIn("1 personal decisions, see the session", page)


if __name__ == "__main__":
    unittest.main()
