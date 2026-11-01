"""Offline tests for tools/context_budget.py: every always-loaded file has a layer and a budget; over budget
is a problem, the band is a warning, an unowned rule is a problem, and the budgets must leave headroom."""
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import context_budget as cb  # noqa: E402


def write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


class BudgetSandbox(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.home = os.path.join(self.tmp.name, "claude")
        self.layers = {}
        for lvl, globs, rules in (("superego", ["regras.md"], ["mapa.md"]), ("ego", ["glossario.md"], []), ("id", ["padroes.md"], ["eu.md"])):
            d = os.path.join(self.tmp.name, lvl)
            write(os.path.join(d, "layer.json"), json.dumps({"level": lvl, "globals": globs, "rules": rules}))
            self.layers[lvl] = d
            for g in globs:
                write(os.path.join(self.home, g), "x" * 100)
            for r in rules:
                write(os.path.join(self.home, "rules", r), "y" * 50)
        write(os.path.join(self.home, "harness", "codex.md"), "z" * 40)
        write(os.path.join(self.home, "CLAUDE.md"), "r" * 20)
        self.budgets = {"superego": 200, "ego": 200, "id": 200, "adapter": 100, "root": 100}
        self.manifest = os.path.join(self.tmp.name, "manifest.json")
        self.write_manifest()

    def write_manifest(self) -> None:
        write(self.manifest, json.dumps({"default_level": "ego", "budgets": self.budgets, "layers": [
            {"level": lvl, "path": d.replace(os.sep, "/"), "active": True} for lvl, d in self.layers.items()]}))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_sizes_are_attributed_per_layer_and_pass_within_budget(self) -> None:
        rep = cb.report(self.manifest, self.home)
        self.assertEqual(rep["problems"], [])
        self.assertEqual(rep["layers"]["superego"]["bytes"], 150)
        self.assertEqual(rep["layers"]["id"]["bytes"], 150)
        self.assertEqual(rep["layers"]["adapter"]["bytes"], 40)
        self.assertEqual(rep["loaded"], 150 + 100 + 150 + 40 + 20)

    def test_over_budget_is_a_problem_and_the_band_a_warning(self) -> None:
        self.budgets["superego"] = 140
        self.budgets["id"] = 160  # 150/160 = 93%: in the band
        self.write_manifest()
        rep = cb.report(self.manifest, self.home)
        self.assertTrue(any(p.startswith("superego:") and "over its budget" in p for p in rep["problems"]), rep["problems"])
        self.assertTrue(any(w.startswith("id:") for w in rep["warnings"]), rep["warnings"])

    def test_an_unowned_rule_or_a_layer_without_budget_is_a_problem(self) -> None:
        write(os.path.join(self.home, "rules", "orfa.md"), "o" * 10)
        del self.budgets["ego"]
        self.write_manifest()
        rep = cb.report(self.manifest, self.home)
        self.assertTrue(any("rules/orfa.md" in p for p in rep["problems"]), rep["problems"])
        self.assertTrue(any(p.startswith("ego:") and "no budget" in p for p in rep["problems"]), rep["problems"])

    def test_budgets_must_leave_headroom_under_the_limit(self) -> None:
        self.budgets["superego"] = cb.LIMIT
        self.write_manifest()
        rep = cb.report(self.manifest, self.home)
        self.assertTrue(any("budgets sum to" in p for p in rep["problems"]), rep["problems"])

    def test_repo_sizes_read_the_checkout(self) -> None:
        d = os.path.join(self.tmp.name, "repo")
        write(os.path.join(d, "global", "a.md"), "abc")
        write(os.path.join(d, "rules", "b.md"), "de")
        write(os.path.join(d, "global", "ignored.json"), "{}")
        self.assertEqual(cb.repo_sizes(d), {"global/a.md": 3, "rules/b.md": 2})


class LiveManifestTest(unittest.TestCase):
    """The real manifest, when present on this machine, keeps every layer within budget (same check CI runs)."""

    def test_live_context_within_budget(self) -> None:
        manifest = os.path.expanduser("~/Codes/psique/manifest.json")
        home = os.path.expanduser("~/.claude")
        if not (os.path.isfile(manifest) and os.path.isdir(home)):
            self.skipTest("no live manifest here")
        rep = cb.report(manifest, home)
        self.assertEqual(rep["problems"], [], rep["problems"])


if __name__ == "__main__":
    unittest.main()
