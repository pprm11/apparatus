"""Offline tests for tools/context_budget.py: every always-loaded file has a layer and a budget; over budget
is a problem, the band is a warning and a gate (check_write, --list-band, --repo --budget), an unowned rule is
a problem, and the budgets must leave headroom. HookTest runs scripts/hook-context-budget.py as Claude would."""
import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import context_budget as cb  # noqa: E402


def write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def write_bytes(path: str, data: bytes) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(data)


class Sandbox(unittest.TestCase):
    """A fake ~/.claude with three layers (superego 150 bytes, ego 100, id 150), an adapter and a root CLAUDE.md.
    Budgets of 200 put the superego band at 180: a 100-byte global may grow to 130 and no further."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.home = os.path.join(self.tmp.name, "claude")
        self.layers = {}
        self.layer_cfg = {}
        for lvl, globs, rules in (("superego", ["rules.md"], ["map.md"]), ("ego", ["glossary.md"], []), ("id", ["patterns.md"], ["me.md"])):
            d = os.path.join(self.tmp.name, lvl)
            self.layer_cfg[lvl] = {"level": lvl, "globals": globs, "rules": rules}
            write(os.path.join(d, "layer.json"), json.dumps(self.layer_cfg[lvl]))
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

    def check(self, relp: str, new_bytes: int) -> str | None:
        return cb.check_write(self.manifest, self.home, os.path.join(self.home, relp), new_bytes)


class BudgetSandbox(Sandbox):
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

    def test_band_boundary_is_exactly_ninety_percent(self) -> None:
        self.budgets["id"] = 167  # int(167 * 0.9) = 150: 150 bytes sit exactly on the line and pass
        self.write_manifest()
        self.assertEqual(cb.report(self.manifest, self.home)["warnings"], [])
        self.budgets["id"] = 166  # int(166 * 0.9) = 149: one byte over the line
        self.write_manifest()
        self.assertEqual(len(cb.report(self.manifest, self.home)["warnings"]), 1)

    def test_an_unowned_rule_or_a_layer_without_budget_is_a_problem(self) -> None:
        write(os.path.join(self.home, "rules", "orphan.md"), "o" * 10)
        del self.budgets["ego"]
        self.write_manifest()
        rep = cb.report(self.manifest, self.home)
        self.assertTrue(any("rules/orphan.md" in p for p in rep["problems"]), rep["problems"])
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

    def test_repo_sizes_follow_layer_json_when_present(self) -> None:
        d = os.path.join(self.tmp.name, "repo")
        write(os.path.join(d, "layer.json"), json.dumps({"level": "superego", "globals": ["a.md", "c.json"], "rules": ["b.md"]}))
        write(os.path.join(d, "global", "a.md"), "abc")
        write(os.path.join(d, "global", "not-loaded.md"), "n" * 500)  # in global/ but not in layer.json
        write(os.path.join(d, "rules", "b.md"), "de")
        self.assertEqual(cb.repo_sizes(d), {"global/a.md": 3, "rules/b.md": 2})

    def test_repo_sizes_and_layer_files_find_a_layer_json_nested_under_superego(self) -> None:
        d = os.path.join(self.tmp.name, "apparatus")  # the superego repo after the pre-1.0 rename
        write(os.path.join(d, "superego", "layer.json"), json.dumps({"level": "superego", "globals": ["a.md"], "rules": ["b.md"]}))
        write(os.path.join(d, "superego", "global", "a.md"), "abc")
        write(os.path.join(d, "superego", "rules", "b.md"), "de")
        write(os.path.join(d, "global", "stray.md"), "s" * 100)  # not the layer
        self.assertEqual(cb.repo_sizes(d), {"superego/global/a.md": 3, "superego/rules/b.md": 2})
        man = {"layers": [{"level": "superego", "path": d.replace(os.sep, "/"), "active": True}]}
        self.assertEqual([rel.replace(os.sep, "/") for rel in (os.path.relpath(p, self.home) for p in cb.layer_files(man, self.home)["superego"])],
                         ["a.md", "rules/b.md"])

    def test_adapter_budget_covers_the_largest_harness_file(self) -> None:
        write(os.path.join(self.home, "harness", "claude.md"), "z" * 70)
        rep = cb.report(self.manifest, self.home)
        self.assertEqual(rep["layers"]["adapter"]["bytes"], 70)
        self.assertEqual(rep["loaded"], 150 + 100 + 150 + 70 + 20)

    def test_band_layers_lists_the_flagged_budget_keys(self) -> None:
        self.assertEqual(cb.band_layers(cb.report(self.manifest, self.home)), [])
        self.budgets["id"] = 160  # 150/160 = 93%
        self.budgets["superego"] = 140  # over budget
        self.write_manifest()
        self.assertEqual(cb.band_layers(cb.report(self.manifest, self.home)), ["superego", "id"])

    def test_candidates_are_the_largest_sections_and_long_bullets(self) -> None:
        write(os.path.join(self.home, "rules.md"), "# T\n\n## Small\n\nab\n\n## Big\n\n- **Long item**: " + "x" * 300
              + "\n- short\n" + "y" * 50 + "\n\n## Mid\n\n" + "m" * 120 + "\n")
        rep = cb.report(self.manifest, self.home)
        cuts = cb.candidates(rep["layers"]["superego"]["files"], self.home, n=3)
        self.assertEqual([c[0] for c in cuts], ["rules.md § Big", "rules.md § Long item", "rules.md § Mid"])
        self.assertGreater(cuts[0][1], cuts[1][1])
        self.assertEqual(cuts[2][1], 120)

    def test_candidates_see_the_preamble_skip_fenced_code_and_read_crlf(self) -> None:
        write_bytes(os.path.join(self.home, "rules.md"),
                    b"intro " * 20 + b"\r\n\r\n## A\r\n\r\n```\r\n# not a heading\r\n- **not a bullet**: " + b"c" * 300
                    + b"\r\n```\r\nbody\r\n")
        rep = cb.report(self.manifest, self.home)
        labels = [c[0] for c in cb.candidates(rep["layers"]["superego"]["files"], self.home)]
        self.assertIn("rules.md § preamble", labels)
        self.assertIn("rules.md § A", labels)
        self.assertNotIn("rules.md § not a heading", labels)
        self.assertNotIn("rules.md § not a bullet", labels)
        # a file with no heading and no long bullet is one candidate by itself
        self.assertEqual(cb.candidates({"rules/map.md": 50}, self.home), [("rules/map.md", 50)])

    def test_check_write_refuses_growth_over_the_band_and_allows_shrinking(self) -> None:
        self.assertIsNone(self.check("rules.md", 130))  # 180: exactly on the line
        self.assertIsNone(self.check("rules.md", 10))  # shrinking always passes
        msg = self.check("rules.md", 131)  # 181: one byte over
        self.assertIn("superego layer would reach 181", msg)
        self.assertIn("room left 30", msg)
        self.assertIn("move the detail to a skill", msg)
        self.assertIsNone(self.check("skills/s/SKILL.md", 10**6))  # not always loaded
        self.assertIsNone(self.check("harness/codex.md", 90))  # adapter: the largest file counts, band at 90
        self.assertIn("adapter layer would reach 95", self.check("harness/codex.md", 95))
        write(os.path.join(self.home, "harness", "claude.md"), "z" * 80)  # another adapter already at 80
        self.assertIsNone(self.check("harness/codex.md", 80))  # max(80, 80) = 80
        self.assertIn("adapter layer would reach 91", self.check("harness/codex.md", 91))

    def test_check_write_and_new_or_unlisted_rules(self) -> None:
        self.assertIn("no layer.json lists it", self.check("rules/new.md", 1))  # creating an unlisted rule
        write(os.path.join(self.home, "rules", "orphan.md"), "o" * 10)
        self.assertIsNone(self.check("rules/orphan.md", 5000))  # existing unlisted rule: report flags it, the edit passes
        self.assertIsNone(self.check("rules/deep/x.md", 1))  # not a direct child: not loaded
        self.layer_cfg["superego"]["rules"].append("new.md")  # listed but not yet created
        write(os.path.join(self.layers["superego"], "layer.json"), json.dumps(self.layer_cfg["superego"]))
        self.assertIsNone(self.check("rules/new.md", 30))  # 150 + 30 = 180
        self.assertIn("superego layer would reach 181", self.check("rules/new.md", 31))
        os.remove(os.path.join(self.layers["superego"], "layer.json"))  # the layer repo is gone or on another branch
        self.assertIsNone(self.check("rules/map.md", 5000))  # an existing rule is never blocked by that

    def _main(self, *argv: str) -> tuple[int, str]:
        out = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
        with mock.patch.object(sys, "argv", ["x", *argv]), contextlib.redirect_stdout(out):
            code = cb.main()
        out.flush()
        return code, out.buffer.getvalue().decode("utf-8")

    def test_repo_mode_fails_over_the_band_of_the_given_budget(self) -> None:
        d = os.path.join(self.tmp.name, "repo")
        write(os.path.join(d, "global", "a.md"), "a" * 95)
        self.assertEqual(self._main("--repo", d, "--budget", "200")[0], 0)
        self.assertEqual(self._main("--repo", d)[0], 0)
        self.assertEqual(self._main("--repo", d, "--budget", "106")[0], 0)  # int(106 * 0.9) = 95: on the line
        code, text = self._main("--repo", d, "--budget", "105")  # int(105 * 0.9) = 94
        self.assertEqual(code, 1)
        self.assertIn("over the band: 95 bytes is more than 94", text)

    @unittest.skipUnless(subprocess.run(["git", "--version"], capture_output=True).returncode == 0, "needs git")
    def test_repo_mode_with_a_base_only_fails_on_growth(self) -> None:
        d = os.path.join(self.tmp.name, "repo")
        write(os.path.join(d, "global", "a.md"), "a" * 95)
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@t")
        for args in (["init", "-q", "-b", "main"], ["add", "-A"], ["commit", "-qm", "base"]):
            subprocess.run(["git", "-C", d, *args], check=True, env=env, capture_output=True)
        code, text = self._main("--repo", d, "--base", "HEAD", "--budget", "100")  # in the band, not growing
        self.assertEqual((code, "not growing" in text), (0, True), text)
        write(os.path.join(d, "global", "a.md"), "a" * 96)
        self.assertEqual(self._main("--repo", d, "--base", "HEAD", "--budget", "100")[0], 1)
        write(os.path.join(d, "global", "a.md"), "a" * 94)  # a trim still in the band passes
        self.assertEqual(self._main("--repo", d, "--base", "HEAD", "--budget", "100")[0], 0)

    def test_list_band_prints_one_key_per_line(self) -> None:
        self.budgets["id"] = 160
        self.write_manifest()
        code, text = self._main("--manifest", self.manifest, "--claude-home", self.home, "--list-band")
        self.assertEqual((code, text.split()), (0, ["id"]))

    def test_inbox_item_carries_the_cut_candidates_once(self) -> None:
        import decisions
        self.budgets["id"] = 160
        self.budgets["adapter"] = 100
        write(os.path.join(self.home, "harness", "claude.md"), "## Claude\n\n" + "c" * 95)  # 95 of 100: in the band
        self.write_manifest()
        rep = cb.report(self.manifest, self.home)
        self.assertEqual(len(cb.add_inbox_items(rep, self.home)), 2)
        self.assertEqual(cb.add_inbox_items(rep, self.home), [])
        items = {i["title"]: i for i in decisions.load(self.home)["items"]}
        id_item = next(i for t, i in items.items() if "layer id" in t)
        self.assertIn("Cut candidates", id_item["detail"])
        self.assertIn("patterns.md", id_item["detail"])
        adapter_item = next(i for t, i in items.items() if "layer adapter" in t)
        self.assertIn("harness/claude.md § Claude", adapter_item["detail"])
        self.assertNotIn("codex.md", adapter_item["detail"])  # only the largest adapter counts


class HookTest(Sandbox):
    """scripts/hook-context-budget.py (PreToolUse Edit|Write) refuses the edit that crosses the band: exit 2 with the
    message on stderr; everything else, and any failure, exits 0. Run with -I like Claude does, so the console
    code page (not PYTHONIOENCODING) is what the hook must override."""

    HOOK = os.path.join(ROOT, "superego", "scripts", "hook-context-budget.py")

    def run_hook(self, event: object, **env_extra: str) -> subprocess.CompletedProcess:
        env = dict(os.environ, CONTEXT_BUDGET_MANIFEST=self.manifest, CLAUDE_HOME=self.home,
                   SUPEREGO_TOOLS=os.path.join(ROOT, "tools"))
        env.update(env_extra)
        payload = event if isinstance(event, str) else json.dumps(event, ensure_ascii=False)
        return subprocess.run([sys.executable, "-I", self.HOOK], input=payload.encode("utf-8"), capture_output=True,
                              env=env, timeout=120)

    def edit(self, relp: str, old: str, new: str, **more: object) -> subprocess.CompletedProcess:
        return self.run_hook({"tool_name": "Edit", "tool_input": {"file_path": os.path.join(self.home, relp),
                                                                  "old_string": old, "new_string": new, **more}})

    def write_event(self, relp: str, content: str) -> subprocess.CompletedProcess:
        return self.run_hook({"tool_name": "Write", "tool_input": {"file_path": os.path.join(self.home, relp), "content": content}})

    def test_edit_that_crosses_the_band_is_refused_with_the_room_left(self) -> None:
        r = self.edit("rules.md", "x", "x" * 50)  # 100 bytes becomes 149: superego 199 of 200
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn(b"room left 30", r.stderr)
        self.assertIn(b"move the detail to a skill", r.stderr)
        self.assertEqual(self.edit("rules.md", "x", "x" * 31).returncode, 0)  # 130: exactly on the line
        self.assertEqual(self.edit("rules.md", "x", "x" * 32).returncode, 2)  # 131

    def test_accented_text_is_counted_in_utf8_and_matched_in_the_file(self) -> None:
        self.assertEqual(self.write_event("rules.md", "ü" * 60).returncode, 0)  # 120 bytes: 170 of 200
        r = self.write_event("rules.md", "ü" * 70)  # 140 bytes: 190
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn("would reach 190".encode("utf-8"), r.stderr)
        write(os.path.join(self.home, "rules.md"), "über" * 16 + "x" * 20)  # 16 * 5 + 20 = 100 bytes with a 2-byte letter
        self.assertEqual(self.edit("rules.md", "über", "über" + "x" * 30).returncode, 0)  # 130
        self.assertEqual(self.edit("rules.md", "über", "über" + "x" * 31).returncode, 2)  # 131: the umlaut matched

    def test_replace_all_missing_old_string_and_crlf_files(self) -> None:
        self.assertEqual(self.edit("rules.md", "x", "xy").returncode, 0)  # one replacement: 101
        self.assertEqual(self.edit("rules.md", "x", "xy", replace_all=True).returncode, 2)  # 200
        self.assertEqual(self.edit("rules.md", "absent", "x" * 500).returncode, 0)  # nothing to replace: passes
        write_bytes(os.path.join(self.home, "rules.md"), b"x\r\n" * 50)  # 100 bytes once CRLF counts as LF
        self.assertEqual(self.write_event("rules.md", "x\r\n" * 65).returncode, 0)  # 130
        self.assertEqual(self.write_event("rules.md", "x\r\n" * 66).returncode, 2)  # 132
        self.assertEqual(self.edit("rules.md", "x\n", "x\n" * 16).returncode, 0)  # 130
        self.assertEqual(self.edit("rules.md", "x\n", "x\n" * 17).returncode, 2)  # 132

    def test_shrinking_other_files_and_other_tools_pass(self) -> None:
        self.assertEqual(self.write_event("rules.md", "x" * 10).returncode, 0)
        outside = os.path.join(self.tmp.name, "other.md")
        self.assertEqual(self.run_hook({"tool_name": "Write", "tool_input": {"file_path": outside, "content": "x" * 10**5}}).returncode, 0)
        self.assertEqual(self.write_event("skills/s/SKILL.md", "x" * 10**5).returncode, 0)
        self.assertEqual(self.write_event("projects/p/memory/m.md", "x" * 10**5).returncode, 0)
        self.assertEqual(self.run_hook({"tool_name": "Bash", "tool_input": {"command": "ls"}}).returncode, 0)

    def test_new_rule_without_a_layer_is_refused_and_a_broken_event_passes(self) -> None:
        r = self.write_event("rules/new.md", "r")
        self.assertEqual(r.returncode, 2, r.stderr)
        self.assertIn(b"no layer.json lists it", r.stderr)
        self.assertEqual(self.run_hook("not json").returncode, 0)

    def test_without_check_write_in_the_tools_the_hook_fails_open_and_says_so(self) -> None:
        old_tools = os.path.join(self.tmp.name, "old-tools")
        write(os.path.join(old_tools, "context_budget.py"), "BAND = 0.9\n")
        r = self.run_hook({"tool_name": "Edit", "tool_input": {"file_path": os.path.join(self.home, "rules.md"),
                                                                "old_string": "x", "new_string": "x" * 500}}, SUPEREGO_TOOLS=old_tools)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn(b"has no check_write", r.stderr)


class LiveManifestTest(unittest.TestCase):
    """The real manifest, when present on this machine, keeps every layer within budget (same check CI runs)."""

    def test_live_context_within_budget(self) -> None:
        import roots
        manifest = roots.default_manifest(None)
        home = os.path.expanduser("~/.claude")
        if not (os.path.isfile(manifest) and os.path.isdir(home)):
            self.skipTest("no live manifest here")
        rep = cb.report(manifest, home)
        self.assertEqual(rep["problems"], [], rep["problems"])


if __name__ == "__main__":
    unittest.main()
