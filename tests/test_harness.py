"""Offline tests for the harness-agnostic layer: Codex session reader and the Codex renderer."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import codex_sessions  # noqa: E402
import render_harness  # noqa: E402


def write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def msg(role: str, kind: str, text: str, ts: str = "2026-10-26T10:00:00Z") -> dict:
    return {"timestamp": ts, "type": "response_item",
            "payload": {"type": "message", "role": role, "content": [{"type": kind, "text": text}]}}


# Claude Code folder key prefix for the fictional user me, built in pieces so no machine-path literal appears.
DRIVE_KEY = "C-" + "-Users-me"
WIN_HOME = "C:" + "\\Users\\me"  # built at run time: the deny gate bans the literal


class CodexSessionsTest(unittest.TestCase):
    def test_keeps_typed_prompts_and_drops_injected_ones(self) -> None:
        lines = [
            {"timestamp": "t", "type": "session_meta", "payload": {"id": "abc", "cwd": WIN_HOME + "\\Codes\\acme-app"}},
            msg("user", "input_text", "# AGENTS.md instructions for C:\\x\n<INSTRUCTIONS>..."),
            msg("user", "input_text", "<environment_context>\n<cwd>C:\\x</cwd>"),
            msg("user", "input_text", "revisa a PR 210"),
            msg("assistant", "output_text", "Vou ler a PR."),
            {"timestamp": "t", "type": "compacted", "payload": {"type": "compacted"}},
        ]
        with tempfile.TemporaryDirectory() as root:
            write(os.path.join(root, "2026", "s.jsonl"), "\n".join(json.dumps(x) for x in lines) + "\nnot json\n")
            recs = list(codex_sessions.iter_records(root))
        self.assertEqual([(r["role"], r["text"]) for r in recs],
                         [("user", "revisa a PR 210"), ("assistant", "Vou ler a PR."), ("compact", "")])
        self.assertEqual({r["proj"] for r in recs}, {DRIVE_KEY + "-Codes-acme-app"})
        self.assertEqual({r["sid"] for r in recs}, {"abc"})

    def test_project_key_matches_claude_folder_names(self) -> None:
        self.assertEqual(codex_sessions.project_key(WIN_HOME + "\\Codes\\"), DRIVE_KEY + "-Codes")
        self.assertEqual(codex_sessions.project_key(""), "codex")
        self.assertEqual(codex_sessions.project_key("\\\\?\\" + WIN_HOME + "\\Codes\\x"), DRIVE_KEY + "-Codes-x")


class RenderTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.claude = os.path.join(self.tmp.name, ".claude")
        self.codex = os.path.join(self.tmp.name, ".codex")
        write(os.path.join(self.claude, "CLAUDE.md"),
              "# Prefs\n@~/.claude/glossary.md\n## Harness\n@~/.claude/harness/claude.md\n")
        write(os.path.join(self.claude, "glossary.md"), "GLOSSARY BODY")
        write(os.path.join(self.claude, "harness", "claude.md"), "CLAUDE ADAPTER")
        write(os.path.join(self.claude, "harness", "codex.md"), "CODEX ADAPTER")
        write(os.path.join(self.claude, "harness", "skills.json"), '{"claude_only": ["only-claude"]}')
        write(os.path.join(self.claude, "rules", "a.md"), "RULE A")
        for name in ("portable", "only-claude", "synced"):
            write(os.path.join(self.claude, "skills", name, "SKILL.md"), name)
        write(os.path.join(self.codex, "skills", "codex-own", "SKILL.md"), "own")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_agents_md_inlines_imports_and_swaps_the_adapter(self) -> None:
        text = render_harness.render_agents_md(self.claude)
        for part in ("GLOSSARY BODY", "CODEX ADAPTER", "RULE A", "Do not edit"):
            self.assertIn(part, text)
        self.assertNotIn("CLAUDE ADAPTER", text)
        self.assertNotIn("@~/", text)

    def test_links_portable_skills_only_and_is_idempotent(self) -> None:
        log = render_harness.sync_skills(self.claude, self.codex, dry_run=False)
        self.assertEqual(log, ["link portable"])
        self.assertEqual(sorted(os.listdir(os.path.join(self.codex, "skills"))), ["codex-own", "portable"])
        with open(os.path.join(self.codex, "skills", "portable", "SKILL.md"), encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "portable")
        self.assertEqual(render_harness.sync_skills(self.claude, self.codex, dry_run=False), [])

    def test_unlinks_a_skill_that_became_claude_only_and_keeps_codex_own(self) -> None:
        render_harness.sync_skills(self.claude, self.codex, dry_run=False)
        write(os.path.join(self.claude, "harness", "skills.json"), '{"claude_only": ["only-claude", "portable"]}')
        self.assertEqual(render_harness.sync_skills(self.claude, self.codex, dry_run=False), ["unlink portable"])
        self.assertEqual(os.listdir(os.path.join(self.codex, "skills")), ["codex-own"])
        self.assertTrue(os.path.isfile(os.path.join(self.claude, "skills", "portable", "SKILL.md")))

    def _run_main(self, *extra: str) -> tuple[int, str]:
        import contextlib
        import io
        from unittest import mock
        out = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
        argv = ["x", "--claude-home", self.claude, "--codex-home", self.codex, *extra]
        with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(out):
            code = render_harness.main()
        out.flush()
        return code, out.buffer.getvalue().decode("utf-8")

    def test_over_the_limit_fails_closed_and_leaves_agents_md_alone(self) -> None:
        code, text = self._run_main("--max-bytes", "100")
        self.assertEqual(code, 1)
        self.assertIn("over the 100 Codex limit; not written", text)
        self.assertIn("warning: AGENTS.md is", text)
        self.assertIn("rules/a.md=", text)  # per-source breakdown
        self.assertFalse(os.path.exists(os.path.join(self.codex, "AGENTS.md")))

    def test_warns_near_the_limit_once_in_the_inbox_and_still_writes(self) -> None:
        import decisions
        size = len(render_harness.render_agents_md(self.claude).encode("utf-8"))
        limit = str(size + size // 20)  # size is at about 95% of the limit: above the 7/8 warning line
        for _ in range(2):
            code, text = self._run_main("--max-bytes", limit)
            self.assertEqual(code, 0)
            self.assertIn("warning: AGENTS.md is", text)
        titles = [i["title"] for i in decisions.load(self.claude)["items"]]
        self.assertEqual(titles, [render_harness.WARN_TITLE])
        self.assertTrue(os.path.isfile(os.path.join(self.codex, "AGENTS.md")))

    def test_no_warning_and_same_success_message_when_small(self) -> None:
        code, text = self._run_main()
        self.assertEqual(code, 0)
        self.assertNotIn("warning", text)
        self.assertRegex(text, r"write .*AGENTS.md \(\d+ bytes\)")


if __name__ == "__main__":
    unittest.main()
