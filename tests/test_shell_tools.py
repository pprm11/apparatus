"""Offline tests for tools/mirror.py and tools/validate_harvest.py."""
import os
import shutil
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import mirror  # noqa: E402
import validate_harvest as vh  # noqa: E402


def write(path: str, text: str = "x\n") -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def tree(root: str) -> set:
    out = set()
    for dp, _, files in os.walk(root):
        for f in files:
            out.add(os.path.relpath(os.path.join(dp, f), root).replace("\\", "/"))
    return out


class MirrorTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cc-mirror-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.src, self.dst = os.path.join(self.tmp, "s"), os.path.join(self.tmp, "d")

    def run_mirror(self, **kw):
        warnings = []
        n = mirror.mirror(self.src, self.dst, set(mirror.DEFAULT_XD) | set(kw.get("xd", ())),
                          set(kw.get("xp", ())), kw.get("delete", True), warnings)
        return n, warnings

    def test_copy_delete_and_excludes(self):
        write(os.path.join(self.src, "a.md"))
        write(os.path.join(self.src, "sub", "b.md"))
        write(os.path.join(self.src, "sub", "__pycache__", "c.pyc"))
        write(os.path.join(self.src, "synced", "d.md"))
        write(os.path.join(self.dst, "stale.md"))
        write(os.path.join(self.dst, "gone", "e.md"))
        self.run_mirror(xp=["synced"])
        self.assertEqual(tree(self.dst), {"a.md", "sub/b.md"})

    def test_second_run_copies_nothing_and_changes_are_picked_up(self):
        write(os.path.join(self.src, "a.md"), "one\n")
        self.assertEqual(self.run_mirror()[0], 1)
        self.assertEqual(self.run_mirror()[0], 0)
        write(os.path.join(self.src, "a.md"), "longer text\n")
        self.assertEqual(self.run_mirror()[0], 1)
        with open(os.path.join(self.dst, "a.md"), encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "longer text\n")

    def test_no_delete_keeps_extra_files(self):
        write(os.path.join(self.src, "a.md"))
        write(os.path.join(self.dst, "keep.md"))
        self.run_mirror(delete=False)
        self.assertEqual(tree(self.dst), {"a.md", "keep.md"})

    def test_permission_error_is_retried_then_reported(self):
        calls = []

        def boom():
            calls.append(1)
            raise PermissionError("held")

        warnings = []
        real_sleep = time.sleep
        mirror.time.sleep = lambda s: None
        try:
            self.assertFalse(mirror.retry(boom, "f", warnings))
        finally:
            mirror.time.sleep = real_sleep
        self.assertEqual(len(calls), 3)
        self.assertEqual(len(warnings), 1)


class ValidateHarvestTest(unittest.TestCase):
    GOOD = "---\nname: {n}\ndescription: d\nmetadata:\n  type: {t}\n  keywords: a\n---\nbody\n"

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cc-vh-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.out = os.path.join(self.tmp, "out", "memory")
        self.projects = os.path.join(self.tmp, "projects")
        os.makedirs(os.path.join(self.projects, "P", "memory"))

    def put(self, name, text, proj="P"):
        write(os.path.join(self.out, proj, name), text)

    def result(self):
        return vh.validate(self.out, self.projects)

    def test_accepts_valid_file_and_index_line(self):
        self.put("a.md", self.GOOD.format(n="a", t="project"))
        self.put("MEMORY.add", "- [A](a.md) — hook\n")
        self.assertEqual(self.result(), ["OK\tP/a.md", "ADD\tP\t- [A](a.md) — hook"])

    def test_rejections(self):
        self.put("a.md", "no frontmatter\n")
        self.put("b.md", self.GOOD.format(n="other", t="project"))
        self.put("c.md", "---\nname: c\ndescription: d\n---\nbody\n")
        self.put("d.md", self.GOOD.format(n="d", t="project") + "x" * 9000)
        self.put("MEMORY.md", "index\n")
        self.put("e.md", self.GOOD.format(n="e", t="project"), proj="NoSuchProject")
        reasons = {line.split("\t")[1]: line.split("\t")[2] for line in self.result() if line.startswith("REJECT")}
        self.assertIn("no frontmatter", reasons["P/a.md"])
        self.assertIn("differs", reasons["P/b.md"])
        self.assertIn("metadata.type", reasons["P/c.md"])
        self.assertIn("8 KB", reasons["P/d.md"])
        self.assertIn("index", reasons["P/MEMORY.md"])
        self.assertIn("does not exist", reasons["NoSuchProject/e.md"])

    def test_never_overwrites_feedback_user_or_pinned(self):
        mem = os.path.join(self.projects, "P", "memory")
        write(os.path.join(mem, "f.md"), self.GOOD.format(n="f", t="feedback"))
        write(os.path.join(mem, "u.md"), self.GOOD.format(n="u", t="user"))
        write(os.path.join(mem, "p.md"), self.GOOD.format(n="p", t="project").replace("keywords: a", "pinned: true"))
        write(os.path.join(mem, "r.md"), self.GOOD.format(n="r", t="reference"))
        for n in "fupr":
            self.put(f"{n}.md", self.GOOD.format(n=n, t="project"))
        got = {line.split("\t")[0] + " " + line.split("\t")[1] for line in self.result()}
        self.assertEqual(got, {"REJECT P/f.md", "REJECT P/u.md", "REJECT P/p.md", "OK P/r.md"})

    def test_at_most_three_files(self):
        for n in "abcd":
            self.put(f"{n}.md", self.GOOD.format(n=n, t="project"))
        kinds = [line.split("\t")[0] for line in self.result()]
        self.assertEqual(kinds, ["OK", "OK", "OK", "REJECT"])

    def test_index_line_skipped_when_already_linked_or_unaccepted(self):
        write(os.path.join(self.projects, "P", "memory", "MEMORY.md"), "- [A](a.md) — old\n")
        self.put("a.md", self.GOOD.format(n="a", t="project"))
        self.put("MEMORY.add", "- [A](a.md) — new\n- [Z](z.md) — not written\n")
        res = self.result()
        self.assertEqual(res[0], "OK\tP/a.md")
        self.assertFalse(any(line.startswith("ADD") for line in res))
        self.assertEqual(sum(line.startswith("REJECT") for line in res), 1)


if __name__ == "__main__":
    unittest.main()
