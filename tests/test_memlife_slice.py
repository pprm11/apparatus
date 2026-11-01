"""Offline tests for memlife slice 1: secret gate, lint warnings for kind/review_by, decay review_by dry-run."""
import json
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

TOOLS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools")
sys.path.insert(0, TOOLS)
import decay  # noqa: E402
import lint_memory  # noqa: E402
import secret_gate  # noqa: E402

# Built at run time so no secret-shaped literal sits in the repo.
FAKE = "x" * 12 + "9Zq4"
ASSIGN = "API" + "_KEY=" + FAKE
GH = "gh" + "p_" + "A" * 24


def write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


class SecretGateTest(unittest.TestCase):
    def test_assignment_and_token_are_found_with_line_and_kind(self) -> None:
        hits = secret_gate.find_secrets(f"ok\n{ASSIGN}\nmore\n{GH}\n")
        self.assertIn((2, "assignment"), hits)
        self.assertIn((4, "github_token"), hits)

    def test_negative_control_placeholders_and_prose_pass(self) -> None:
        text = "API_KEY=$API_KEY\ntoken: <token>\nsecret management is a topic\nsenha=abc\nmail " + "a" + "@" + "b.test http://x.io\n"
        self.assertEqual(secret_gate.find_secrets(text), [])

    def test_cli_never_prints_the_value(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "m.md")
            write(path, f"line\n{ASSIGN}\n")
            run = subprocess.run([sys.executable, "-I", os.path.join(TOOLS, "secret_gate.py"), path],
                                 capture_output=True, text=True)
            self.assertEqual(run.returncode, 1)
            self.assertIn(":2 assignment", run.stdout)
            self.assertNotIn(FAKE, run.stdout + run.stderr)
            clean = os.path.join(tmp, "c.md")
            write(clean, "nothing here\n")
            self.assertEqual(subprocess.run([sys.executable, "-I", os.path.join(TOOLS, "secret_gate.py"), clean]).returncode, 0)

    def test_hook_is_off_by_default_and_blocks_only_when_flag_is_on(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "synthetic-home", "projects", "P", "memory", "m.md")
            write(path, f"---\nname: m\n---\n{ASSIGN}\n")
            event = json.dumps({"tool_input": {"file_path": path}})
            copy_tools = Path(tmp) / "sandbox-repo" / "tools"
            shutil.copytree(TOOLS, copy_tools)
            sentinel_index = copy_tools.parent / "index" / "search-index.json"
            sentinel_catalog = copy_tools.parent / "INDEX.md"
            sentinel_index.parent.mkdir()
            sentinel_index.write_text("index sentinel", encoding="utf-8")
            sentinel_catalog.write_text("catalog sentinel", encoding="utf-8")
            hook = str(copy_tools / "index_hook.py")
            env = {k: v for k, v in os.environ.items() if k != "MEMLIFE_SECRET_GATE"}
            env.update({"CLAUDE_CONFIG_DIR": os.path.join(tmp, "synthetic-home"), "HOME": tmp, "USERPROFILE": tmp})
            for key in ("CODEX_HOME", "HOMEDRIVE", "HOMEPATH", "COMPANIES_FILE"):
                env.pop(key, None)
            off = subprocess.run([sys.executable, "-I", hook], input=event, capture_output=True, text=True, env=env)
            self.assertEqual(off.returncode, 0)
            self.assertTrue((Path(tmp) / "synthetic-home" / ".search-memory" / "search-index.json").is_file())
            on = subprocess.run([sys.executable, "-I", hook], input=event, capture_output=True, text=True,
                                env={**env, "MEMLIFE_SECRET_GATE": "1"})
            self.assertEqual(on.returncode, 2)
            self.assertNotIn(FAKE, on.stdout + on.stderr)
            self.assertEqual(sentinel_index.read_text(encoding="utf-8"), "index sentinel")
            self.assertEqual(sentinel_catalog.read_text(encoding="utf-8"), "catalog sentinel")


class LintSliceTest(unittest.TestCase):
    def warn(self, front_extra: str, body: str = "b") -> list[str]:
        with tempfile.TemporaryDirectory() as root:
            write(os.path.join(root, "global", "CLAUDE.md"), "x")
            write(os.path.join(root, "memory", "P", "m.md"),
                  f"---\nname: m\ndescription: d\nmetadata:\n  keywords: a, b, c, d, e, f\n  modified: 2026-10-20\n"
                  f"  type: project\n{front_extra}---\n{body}\n")
            return lint_memory.warnings(lint_memory.load(os.path.join(root, "memory")), lint_memory.schema_texts(root))

    def test_unknown_kind_and_bad_review_by_warn(self) -> None:
        out = "\n".join(self.warn("  kind: weird\n  review_by: soon\n"))
        self.assertIn("`metadata.kind` is 'weird'", out)
        self.assertIn("not an ISO date", out)

    def test_negative_control_valid_fields_and_absent_fields_do_not_warn(self) -> None:
        self.assertEqual(self.warn("  kind: decision\n  review_by: 2027-01-31\n"), [])
        self.assertEqual(self.warn(""), [])

    def test_secret_line_is_a_warning_without_the_value(self) -> None:
        out = "\n".join(self.warn("", ASSIGN))
        self.assertIn("looks like a secret", out)
        self.assertNotIn(FAKE, out)


class DecayDueTest(unittest.TestCase):
    def test_due_lists_past_review_by_only_and_changes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as home:
            mem = os.path.join(home, "projects", "P", "memory")
            for name, review in (("past", "2026-01-01"), ("future", "2099-01-01"), ("none", "")):
                extra = f"  review_by: {review}\n" if review else ""
                write(os.path.join(mem, f"{name}.md"), f"---\nname: {name}\nmetadata:\n  type: project\n{extra}---\nb\n")
            before = {n: open(os.path.join(mem, n), encoding="utf-8").read() for n in os.listdir(mem)}
            due = decay.due_for_review(home, now=time.mktime((2026, 10, 30, 0, 0, 0, 0, 0, -1)))
            self.assertEqual([r["name"] for r in due], ["past"])
            after = {n: open(os.path.join(mem, n), encoding="utf-8").read() for n in os.listdir(mem)}
            self.assertEqual(before, after)
            self.assertFalse(os.path.exists(os.path.join(home, "archive")))


if __name__ == "__main__":
    unittest.main()
