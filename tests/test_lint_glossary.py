"""Offline tests for tools/lint_glossary.py: the glossary of every layer exists, keeps the fixed shape, and
terms do not collide across layers unless declared. The templates must pass as shipped."""
import json
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import lint_glossary as lg  # noqa: E402

GOOD = """# Glossário de teste (nível {level})

Versão: v1.0, 01/01/2026.

## Colisões (mesma palavra, coisas diferentes)

| Palavra | Sentidos | Termo padrão |
|---|---|---|
{rows}

## Termos padrão
{terms}

## Como interpretar pedidos
- **pede {level}**: leitura própria desta camada.
"""


def write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


class Sandbox(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.dirs: dict[str, str] = {}

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def layer(self, level: str, terms: str = "- **task**: unidade de trabalho.", rows: str = "", text: str | None = None,
              cfg_extra: dict | None = None) -> str:
        d = os.path.join(self.tmp.name, level)
        cfg = {"level": level, "globals": ["glossario.md"], "glossary": "glossario.md"}
        cfg.update(cfg_extra or {})
        write(os.path.join(d, "layer.json"), json.dumps(cfg))
        body = text if text is not None else GOOD.format(level=level, rows=rows or "| x | a · b | **a** · **b** |", terms=terms)
        write(os.path.join(d, "global", "glossario.md"), body)
        self.dirs[level] = d
        return d

    def run_lint(self) -> tuple[list[str], list[str]]:
        return lg.check(lg.load_layer_dirs(list(self.dirs.values())))


class ShapeTest(Sandbox):
    def test_well_formed_layers_pass(self) -> None:
        self.layer("superego")
        self.layer("ego", terms="- **Acme**: a empresa.")
        problems, warnings = self.run_lint()
        self.assertEqual(problems, [])
        self.assertEqual(warnings, [])

    def test_missing_version_and_sections_are_problems(self) -> None:
        self.layer("ego", text="# Glossário\n\n## Termos padrão\n- **a**: b.\n")
        problems, _ = self.run_lint()
        self.assertTrue(any("Versão" in p for p in problems), problems)
        self.assertTrue(any("Colisões" in p for p in problems), problems)
        self.assertTrue(any("Como interpretar pedidos" in p for p in problems), problems)

    def test_glossary_must_be_declared_present_and_loaded(self) -> None:
        self.layer("ego", cfg_extra={"glossary": None})
        self.layer("id", cfg_extra={"globals": []})
        d = self.layer("superego")
        os.remove(os.path.join(d, "global", "glossario.md"))
        problems, _ = self.run_lint()
        self.assertTrue(any("no `glossary` field" in p for p in problems), problems)
        self.assertTrue(any("not listed in `globals`" in p for p in problems), problems)
        self.assertTrue(any("not found" in p for p in problems), problems)


class CrossLayerTest(Sandbox):
    def test_same_term_different_meaning_is_a_problem_unless_a_collision(self) -> None:
        self.layer("superego", terms="- **onda**: lote de tasks por dependência.")
        self.layer("ego", terms="- **onda**: disparo de campanha.")
        problems, _ = self.run_lint()
        self.assertTrue(any("`onda`" in p and "different texts" in p for p in problems), problems)
        self.layer("ego", terms="- **onda**: disparo de campanha.", rows="| onda | lote de tasks · disparo | **onda** · **onda de disparo** |")
        problems, _ = self.run_lint()
        self.assertEqual(problems, [])

    def test_same_term_same_meaning_is_only_a_warning(self) -> None:
        self.layer("superego", terms="- **task**: unidade de trabalho.")
        self.layer("ego", terms="- **task**: unidade de trabalho.")
        problems, warnings = self.run_lint()
        self.assertEqual(problems, [])
        self.assertTrue(any("`task`" in w and "same definition" in w for w in warnings), warnings)

    def test_superego_may_not_name_a_term_of_another_layer(self) -> None:
        self.layer("superego", terms="- **task**: unidade de trabalho da Acme Checkout.")
        self.layer("ego", terms="- **Acme Checkout**: o produto.")
        problems, _ = self.run_lint()
        self.assertTrue(any("superego glossary mentions `acme checkout`" in p for p in problems), problems)

    def test_oversized_glossary_warns(self) -> None:
        self.layer("id", terms="- **x**: " + "y" * 5000 + ".")
        _, warnings = self.run_lint()
        self.assertTrue(any("bytes" in w for w in warnings), warnings)


class TemplatesAndCliTest(unittest.TestCase):
    def test_shipped_templates_pass(self) -> None:
        dirs = [os.path.join(ROOT, "templates", n) for n in ("ego", "id", "collective")]
        problems, _ = lg.check(lg.load_layer_dirs(dirs))
        self.assertEqual(problems, [], problems)

    def test_this_repo_glossary_passes(self) -> None:
        """The superego's own glossary (global/<glossary>) keeps the shape; CI runs this on every push."""
        problems, _ = lg.check(lg.load_layer_dirs([ROOT]))
        self.assertEqual(problems, [], problems)

    def test_cli_exit_code_follows_problems(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            d = os.path.join(tmp, "ego")
            write(os.path.join(d, "layer.json"), json.dumps({"level": "ego", "globals": ["g.md"], "glossary": "g.md"}))
            write(os.path.join(d, "global", "g.md"), "# g\n")
            res = subprocess.run([sys.executable, "-I", os.path.join(ROOT, "tools", "lint_glossary.py"), "--layer-dir", d],
                                 capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(res.returncode, 1, res.stdout)
            self.assertIn("problems", res.stdout)


if __name__ == "__main__":
    unittest.main()
