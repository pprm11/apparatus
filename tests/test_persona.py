"""The persona level: opinionated, opt-in practices between superego and collective.

Load order: superego, persona, collective, ego, id. Precedence is the reverse (id wins)."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import compose  # noqa: E402
import layers  # noqa: E402


class PersonaLevelTest(unittest.TestCase):
    def test_levels_and_load_order(self) -> None:
        self.assertEqual(layers.LEVELS, ("superego", "persona", "collective", "ego", "id"))
        self.assertEqual(compose.LEVEL_ORDER, layers.LEVELS)
        self.assertIn("persona", compose.SHARED_LEVELS)

    def test_frontmatter_level_persona_is_recognised(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "SKILL.md"
            p.write_text("---\nname: x\nlevel: persona\n---\nbody\n", encoding="utf-8")
            self.assertEqual(layers.frontmatter_level(str(p)), "persona")

    def test_template_is_a_valid_layer(self) -> None:
        cfg = json.loads((ROOT / "templates" / "persona" / "layer.json").read_text(encoding="utf-8"))
        self.assertEqual(cfg["level"], "persona")
        for name in cfg["globals"]:
            self.assertTrue((ROOT / "templates" / "persona" / "global" / name).is_file())

    def test_root_claude_md_lists_persona_between_superego_and_collective(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            home = base / "claude"
            home.mkdir()
            manifest_layers = []
            for level in layers.LEVELS:
                repo = base / level
                repo.mkdir()
                (repo / "layer.json").write_text(json.dumps({"level": level, "globals": [f"{level}.md"]}), encoding="utf-8")
                (home / f"{level}.md").write_text(f"# {level}\n", encoding="utf-8")
                manifest_layers.append({"level": level, "path": str(repo), "active": True, "config": {"globals": [f"{level}.md"]}})
            text = compose.root_claude_md({"layers": manifest_layers}, str(home))
            order = [text.index(f"@~/.claude/{level}.md") for level in layers.LEVELS]
            self.assertEqual(order, sorted(order))


if __name__ == "__main__":
    unittest.main()
