"""A project key longer than the limit (a scratch session without a folder) gets a short, stable folder in the
layer repos, so no exported path passes Windows MAX_PATH. No network, no real ~/.claude."""
import hashlib
import os
import shutil
import subprocess
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import layers  # noqa: E402
import lint_memory  # noqa: E402
from test_layers import LayerSandbox  # noqa: E402
from test_shell_sync import BASH, posix, write  # noqa: E402

LONG = ("home-me-app-data-scratch-workspaces-session-keys-0123456789-" + "a1b2c3d4-" * 15)[:190]
# The fake home sits in a temp dir, so on Windows a 190-character source folder would pass MAX_PATH (260) before
# the code under test runs; the exports below use a 140-character key, long enough to need shortening.
MID = LONG[:140]
OTHER = LONG[:60] + "Z" * (len(LONG) - 60)  # same first 60 characters, different key


class ShortProjectKeyTest(unittest.TestCase):
    def test_a_key_at_or_under_the_limit_is_unchanged(self):
        self.assertEqual(layers.short_project_key("home-me-code-project"), "home-me-code-project")
        edge = "k" * layers.PROJECT_KEY_LIMIT
        self.assertEqual(layers.short_project_key(edge), edge)

    def test_a_long_key_becomes_prefix_and_ten_hex_of_the_hash(self):
        self.assertEqual(len(LONG), 190)
        short = layers.short_project_key(LONG)
        digest = hashlib.sha256(LONG.encode("utf-8")).hexdigest()[:10]
        self.assertEqual(short, f"{LONG[:60]}-{digest}")
        self.assertEqual(short, layers.short_project_key(LONG))  # stable across runs

    def test_two_long_keys_with_the_same_prefix_do_not_collide(self):
        self.assertEqual(LONG[:60], OTHER[:60])
        self.assertNotEqual(layers.short_project_key(LONG), layers.short_project_key(OTHER))


class LongKeyExportTest(LayerSandbox):
    def export_long(self, key=MID, name="email-de-reembolso"):
        self.memory(key, name, "ego")
        layers.export(self.man, self.home, "ego")
        return os.path.join(self.dirs["ego"], "memory", layers.short_project_key(key))

    def test_plan_destination_is_under_200_characters(self):
        self.memory(MID, "email", "ego")
        (_, dst), = [p for p in layers.plan(self.man, self.home)["ego"] if p[0].endswith("email.md")]
        self.assertLess(len(dst), 200)
        self.assertTrue(dst.startswith(f"memory/{layers.short_project_key(MID)}/"))

    def test_the_source_folder_is_not_renamed(self):
        self.memory(MID, "email", "ego")
        (src, _), = [p for p in layers.plan(self.man, self.home)["ego"] if p[0].endswith("email.md")]
        self.assertEqual(src, f"projects/{MID}/memory/email.md")

    def test_export_succeeds_and_writes_the_original_key_into_a_marker(self):
        folder = self.export_long()
        self.assertTrue(os.path.isfile(os.path.join(folder, "email-de-reembolso.md")))
        with open(os.path.join(folder, layers.PROJECT_KEY_MARKER), encoding="utf-8") as fh:
            self.assertEqual(fh.read().strip(), MID)

    def test_the_marker_survives_the_prune_of_the_next_export(self):
        folder = self.export_long()
        layers.export(self.man, self.home, "ego")
        self.assertTrue(os.path.isfile(os.path.join(folder, layers.PROJECT_KEY_MARKER)))

    def test_a_short_key_gets_no_marker(self):
        self.memory("p", "a", "ego")
        layers.export(self.man, self.home, "ego")
        self.assertFalse(self.exists("ego", "memory", "p", layers.PROJECT_KEY_MARKER))

    def test_the_index_of_a_long_key_lands_in_the_short_folder(self):
        self.memory(MID, "mine", "ego")
        self.memory(MID, "theirs", "id")
        write(os.path.join(self.home, "projects", MID, "memory", "MEMORY.md"),
              "# Memory\n- [mine](mine.md) - m\n- [theirs](theirs.md) - t\n")
        layers.export(self.man, self.home, "ego")
        index = os.path.join(self.dirs["ego"], "memory", layers.short_project_key(MID), "MEMORY.md")
        with open(index, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "# Memory\n- [mine](mine.md) - m\n")

    def test_restore_puts_the_memory_back_under_the_original_key(self):
        self.export_long()
        shutil.copy(os.path.join(ROOT, "restore.sh"), os.path.join(self.tmp, "restore.sh"))
        os.makedirs(os.path.join(self.tmp, "tools"))
        for f in os.listdir(os.path.join(ROOT, "tools")):
            if f.endswith(".py"):
                shutil.copy(os.path.join(ROOT, "tools", f), os.path.join(self.tmp, "tools", f))
        target = os.path.join(self.tmp, "restored")
        env = dict(os.environ, HOME=os.path.join(self.tmp, "h"), USERPROFILE=os.path.join(self.tmp, "h"),
                   PYTHONIOENCODING="utf-8")
        r = subprocess.run([BASH, posix(os.path.join(self.tmp, "restore.sh")), "--from", posix(self.dirs["ego"]),
                            "--claude-home", posix(target)], capture_output=True, text=True, encoding="utf-8",
                           env=env, timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        mem = os.path.join(target, "projects", MID, "memory")
        self.assertTrue(os.path.isfile(os.path.join(mem, "email-de-reembolso.md")))
        self.assertFalse(os.path.exists(os.path.join(mem, layers.PROJECT_KEY_MARKER)))
        self.assertFalse(os.path.exists(os.path.join(target, "projects", layers.short_project_key(MID))))


class LintLongKeyTest(LayerSandbox):
    def test_lint_warns_about_the_long_key_and_names_the_folder(self):
        self.memory(MID, "email", "ego")
        layers.export(self.man, self.home, "ego")
        mem = os.path.join(self.dirs["ego"], "memory")
        got = lint_memory.long_key_warnings(mem)
        short = layers.short_project_key(MID)
        self.assertEqual(len(got), 1, got)
        self.assertIn(f"`{short}`", got[0])
        self.assertIn(str(len(MID)), got[0])

    def test_lint_is_quiet_for_short_keys_and_reads_a_raw_long_folder_too(self):
        write(os.path.join(self.tmp, "mem", "p", "a.md"), "x")
        self.assertEqual(lint_memory.long_key_warnings(os.path.join(self.tmp, "mem")), [])
        write(os.path.join(self.tmp, "mem", MID, "a.md"), "x")
        self.assertEqual(len(lint_memory.long_key_warnings(os.path.join(self.tmp, "mem"))), 1)


if __name__ == "__main__":
    unittest.main()
