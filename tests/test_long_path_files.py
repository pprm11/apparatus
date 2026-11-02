"""A memory file whose path in ~/.claude reaches Windows MAX_PATH (260) must be read, indexed and exported.

Origin (2026-11-01): the Claude desktop app keeps a scratch session under a 181-character project key; a memory
file in it has a 260-character path. Plain os.stat/open/copy fail on it with WinError 3 although the file exists:
tools/search_memory.py died with FileNotFoundError ("harvest FAILED (index)") and layers.plan skipped the file
without a word. The fix is ospaths.long_path at each file call; a file that is really unreadable is reported on
stderr and left out of the index, never fatal. On Linux and macOS the long path works unprefixed, so these
tests pass there too (they then only guard against a regression of the helper)."""
import io
import os
import shutil
import sys
import unittest
from contextlib import redirect_stderr
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import layers  # noqa: E402
import mirror  # noqa: E402
import ospaths  # noqa: E402
import search_memory  # noqa: E402
from ospaths import long_path  # noqa: E402
from test_layers import LayerSandbox  # noqa: E402
from test_shell_sync import memory_text  # noqa: E402

WINDOWS = ospaths.system() == ospaths.WINDOWS
BS = chr(92)
NAME = "imagens-coladas-no-chat-viram-arquivo"
TARGET = 262  # characters of the source path; the real failing file had 260


class LongPathHelperTest(unittest.TestCase):
    LONG = "C:/work/" + "d" * 240

    def test_windows_gets_the_extended_prefix_and_backslashes(self):
        out = long_path(self.LONG, "win32")
        self.assertEqual(out, ospaths.EXTENDED_PREFIX + self.LONG.replace("/", BS))
        self.assertTrue(out.startswith(BS * 2 + "?" + BS + "C:" + BS + "work" + BS))

    def test_unc_path_uses_the_unc_form(self):
        out = long_path("//server/share/" + "d" * 240, "win32")
        self.assertTrue(out.startswith(ospaths.EXTENDED_PREFIX + "UNC" + BS + "server" + BS + "share" + BS))

    def test_a_short_path_is_unchanged(self):
        self.assertEqual(long_path("C:/work/x.md", "win32"), "C:/work/x.md")

    def test_linux_and_macos_are_a_no_op(self):
        for plat in ("linux", "darwin"):
            self.assertEqual(long_path(self.LONG, plat), self.LONG)

    def test_it_is_idempotent(self):
        once = long_path(self.LONG, "win32")
        self.assertEqual(long_path(once, "win32"), once)

    def test_it_takes_a_pathlib_path(self):
        from pathlib import PurePosixPath
        self.assertEqual(long_path(PurePosixPath("/a/b"), "linux"), "/a/b")


class LongSourceFileTest(LayerSandbox):
    def setUp(self):
        super().setUp()
        self.addCleanup(shutil.rmtree, long_path(self.tmp), True)  # runs first; the plain rmtree cannot reach it
        fixed = len(os.path.join(self.home, "projects", "", "memory", NAME + ".md"))
        self.key = ("proj-app-data-scratch-workspaces-" + "0123456789abcdef-" * 20)[:TARGET - fixed - 1]
        self.src = os.path.join(self.home, "projects", self.key, "memory", NAME + ".md")
        self.assertEqual(len(self.src), TARGET)
        os.makedirs(long_path(os.path.dirname(self.src)), exist_ok=True)
        with open(long_path(self.src), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(memory_text(NAME, "ego", "pasted images become files"))

    def test_root_cause_plain_calls_fail_on_windows_and_long_path_succeeds(self):
        self.assertTrue(os.path.getmtime(long_path(self.src)) > 0)
        if WINDOWS:
            with self.assertRaises(FileNotFoundError):  # WinError 3, the file is there
                os.path.getmtime(self.src)
            self.assertFalse(os.path.isfile(self.src))

    def test_the_index_builds_and_includes_the_long_file(self):
        index = search_memory.build(self.home)
        self.assertIn(self.src, [d["path"] for d in index["docs"]])
        self.assertGreater(search_memory._newest(self.home), 0)
        self.assertEqual(search_memory.source_fingerprint(self.home), search_memory.source_fingerprint(self.home))

    def test_the_cached_index_is_current_after_a_write(self):
        index_path, catalog_path = os.path.join(self.tmp, "i.json"), os.path.join(self.tmp, "i.md")
        _, rebuilt = search_memory.write_index(self.home, True, index_path, catalog_path)
        self.assertTrue(rebuilt)
        _, rebuilt = search_memory.write_index(self.home, False, index_path, catalog_path)
        self.assertFalse(rebuilt)

    def test_one_unreadable_file_is_reported_and_skipped_not_fatal(self):
        self.memory("p", "fine", "ego")
        bad = os.path.join(self.home, "projects", "p", "memory", "bad.md")
        with open(bad, "w", encoding="utf-8") as fh:
            fh.write(memory_text("bad"))
        real_stat, search_memory._REPORTED = os.stat, set()

        def stat(path, *a, **kw):
            if str(path).endswith("bad.md"):
                raise PermissionError(13, "denied", str(path))
            return real_stat(path, *a, **kw)

        err = io.StringIO()
        with mock.patch.object(search_memory.os, "stat", stat), redirect_stderr(err):
            index = search_memory.build(self.home)
            search_memory.build(self.home)  # a second pass does not repeat the report
        paths = [d["path"] for d in index["docs"]]
        self.assertNotIn(bad, paths)
        self.assertTrue(any(p.endswith("fine.md") for p in paths))
        self.assertIn(self.src, paths)
        self.assertEqual(err.getvalue().count("skipped"), 1)
        self.assertIn("bad.md", err.getvalue())

    def test_plan_lists_the_long_file_under_the_short_key(self):
        (item,) = [p for p in layers.plan(self.man, self.home)["ego"] if p[0].endswith(NAME + ".md")]
        self.assertEqual(item[0], f"projects/{self.key}/memory/{NAME}.md")
        self.assertEqual(item[1], f"memory/{layers.short_project_key(self.key)}/{NAME}.md")
        self.assertLess(len(item[1]), 200)

    def test_export_copies_the_long_file_into_the_short_folder(self):
        log = layers.export(self.man, self.home, "ego")
        dst = os.path.join(self.dirs["ego"], "memory", layers.short_project_key(self.key), NAME + ".md")
        self.assertTrue(os.path.isfile(long_path(dst)), "\n".join(log))
        with open(long_path(dst), encoding="utf-8") as fh:
            self.assertIn("pasted images become files", fh.read())

    def test_the_level_of_a_long_file_is_read_from_its_frontmatter(self):
        self.assertEqual(layers.frontmatter_level(self.src), "ego")
        self.assertEqual(layers.unlabeled(self.home), [])

    def test_mirror_copies_a_tree_with_a_long_file(self):
        dst = os.path.join(self.tmp, "mirror-out")
        warnings: list = []
        copied = mirror.mirror(os.path.join(self.home, "projects"), dst, set(), set(), True, warnings)
        self.assertEqual((copied, warnings), (1, []))
        self.assertTrue(os.path.isfile(long_path(os.path.join(dst, self.key, "memory", NAME + ".md"))))
        self.assertEqual(mirror.mirror(os.path.join(self.home, "projects"), dst, set(), set(), True, warnings), 0)


if __name__ == "__main__":
    unittest.main()
