"""Offline tests for tools/lint_memory.py: the problem count keeps its meaning, warnings sit apart."""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import lint_memory  # noqa: E402

GOOD_KW = "a, b, c, d, e, f"
SCHEMA = ("Nunca mande mensagem em nome do Alex sem pedir permissao explicita antes e sempre mostre o rascunho "
          "completo para ele aprovar com uma palavra clara de confirmacao.")


def write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def memory(root: str, name: str, body: str, keywords: str = GOOD_KW, modified: str = "2026-10-20") -> None:
    mod = f"  modified: {modified}\n" if modified else ""
    kw = f"  keywords: {keywords}\n" if keywords else ""
    write(os.path.join(root, "memory", "P", f"{name}.md"),
          f"---\nname: {name}\ndescription: d\nmetadata:\n{kw}{mod}  type: project\n---\n{body}\n")


class LintTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name
        write(os.path.join(self.root, "global", "CLAUDE.md"), SCHEMA)
        write(os.path.join(self.root, "rules", "r.md"), "Regra curta de teste.")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def warn(self) -> list[str]:
        projects = lint_memory.load(os.path.join(self.root, "memory"))
        return lint_memory.warnings(projects, lint_memory.schema_texts(self.root))

    def test_clean_memory_has_no_warnings(self) -> None:
        memory(self.root, "ok", "fato curto e unico sobre um assunto")
        self.assertEqual(self.warn(), [])

    def test_keywords_outside_range(self) -> None:
        memory(self.root, "few", "x", keywords="a, b")
        memory(self.root, "many", "x", keywords=", ".join("k%d" % i for i in range(16)))
        memory(self.root, "none", "x", keywords="")
        got = "\n".join(self.warn())
        self.assertIn("`P/few.md`: 2 keywords", got)
        self.assertIn("`P/many.md`: 16 keywords", got)
        self.assertIn("`P/none.md`: 0 keywords", got)

    def test_missing_modified(self) -> None:
        memory(self.root, "nomod", "x", modified="")
        self.assertTrue(any("`P/nomod.md`: no `metadata.modified`" in w for w in self.warn()))

    def test_big_body(self) -> None:
        memory(self.root, "big", "palavra " * 500)
        self.assertTrue(any("`P/big.md`: body is" in w for w in self.warn()))

    def test_stale_size_claims(self) -> None:
        memory(self.root, "claim", "O AGENTS.md esta com 27,9 KB de 32 KB hoje")
        memory(self.root, "claim2", "now 29,168 bytes of 32,768 bytes")
        memory(self.root, "fine", "limite de 32 KB sem numero atual")
        got = self.warn()
        self.assertTrue(any("`P/claim.md`" in w and "27,9 KB de 32 KB" in w for w in got))
        self.assertTrue(any("`P/claim2.md`" in w for w in got))
        self.assertFalse(any("`P/fine.md`" in w for w in got))

    def test_near_duplicate_of_schema_file(self) -> None:
        memory(self.root, "dup", SCHEMA + " Mais uma frase propria da memoria.")
        memory(self.root, "unique", "Texto totalmente diferente que nao repete nenhuma regra do esquema carregado sempre.")
        got = self.warn()
        self.assertTrue(any("`P/dup.md`" in w and "`global/CLAUDE.md`" in w for w in got))
        self.assertFalse(any("`P/unique.md`" in w and "near-duplicate" in w for w in got))

    def test_report_keeps_problem_count_apart_and_has_no_day_counts(self) -> None:
        import contextlib
        import io
        from unittest import mock
        memory(self.root, "w", "x", keywords="a")
        out = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
        argv = ["x", os.path.join(self.root, "memory")]
        with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(out):
            lint_memory.main()
        out.flush()
        text = out.buffer.getvalue().decode("utf-8")
        self.assertRegex(text, r"\d+ problems")
        self.assertIn("## Warnings (", text)
        self.assertIn("1 keywords", text)
        self.assertNotRegex(text, r"untouched for \d+ days")


if __name__ == "__main__":
    unittest.main()


class SiblingLayersTest(unittest.TestCase):
    """One memory tree split by level: what resolves in a sibling layer is not a problem."""

    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.ego = os.path.join(self.tmp.name, "ego", "memory")
        self.id = os.path.join(self.tmp.name, "id", "memory")
        write(os.path.join(self.ego, "P", "MEMORY.md"), "- [a](a.md)\n- [b](b.md)\n")
        write(os.path.join(self.ego, "P", "a.md"), f"---\nname: a\ndescription: d\nmetadata:\n  type: project\n---\nsee [[b]]\n")
        write(os.path.join(self.id, "P", "b.md"), f"---\nname: b\ndescription: d\nmetadata:\n  type: user\n---\nsee [[a]]\n")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def run_lint(self, root: str, *siblings: str) -> str:
        import subprocess
        tool = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools", "lint_memory.py")
        args = [sys.executable, "-I", tool, root]
        for s in siblings:
            args += ["--sibling", s]
        return subprocess.run(args, capture_output=True, text=True, encoding="utf-8", check=True).stdout

    def test_alone_each_layer_reports_the_split_as_problems(self) -> None:
        self.assertIn("index points to missing file `b.md`", self.run_lint(self.ego))
        self.assertIn("MEMORY.md missing", self.run_lint(self.id))

    def test_with_siblings_the_split_is_not_a_problem(self) -> None:
        ego = self.run_lint(self.ego, self.id)
        idr = self.run_lint(self.id, self.ego)
        self.assertIn("0 problems", ego, ego)
        self.assertIn("0 problems", idr, idr)

    def test_a_real_broken_link_still_counts(self) -> None:
        write(os.path.join(self.id, "P", "c.md"), "---\nname: c\ndescription: d\nmetadata:\n  type: user\n---\nsee [[nope]]\n")
        out = self.run_lint(self.id, self.ego)
        self.assertIn("link [[nope]] has no memory", out)
        self.assertIn("`P/c.md`: not listed in MEMORY.md", out)

    def test_a_memory_kept_only_sealed_in_a_sibling_counts_as_present(self) -> None:
        write(os.path.join(self.ego, "P", "MEMORY.md"), "- [a](a.md)\n- [b](b.md)\n- [s](s.md)\n")
        write(os.path.join(self.ego, "P", "a.md"), "---\nname: a\ndescription: d\nmetadata:\n  type: project\n---\nsee [[b]] and [[s]]\n")
        write(os.path.join(self.tmp.name, "id", "sealed", "projects", "P", "memory", "s.md.age"), "x")
        out = self.run_lint(self.ego, self.id)
        self.assertIn("0 problems", out, out)
