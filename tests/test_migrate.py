import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import migrate  # noqa: E402

MAP = {"repos": {"old": "new"}, "files": {"rules/old-name.md": "rules/new-name.md"},
       "skills": {"old-skill": "new-skill"}, "retired": {"rules/gone.md": "persona: practices.md"}, "removed_after": "next major"}


class MigrateTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / "claude"
        (self.home / "rules").mkdir(parents=True)
        (self.home / "skills" / "old-skill").mkdir(parents=True)
        (self.home / "rules" / "old-name.md").write_text("x\n", encoding="utf-8")
        (self.home / "rules" / "gone.md").write_text("g\n", encoding="utf-8")
        (self.home / "CLAUDE.md").write_text("@~/.claude/rules/old-name.md\n@~/.claude/rules/keep.md\n", encoding="utf-8")
        self.manifest = Path(self.tmp.name) / "manifest.json"
        self.manifest.write_text(json.dumps({"layers": [
            {"level": "superego", "path": "x", "repo": "git@github.com:acme/old.git"},
            {"level": "id", "path": "y", "repo": "git@github.com:acme/other.git"}]}), encoding="utf-8")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_the_shipped_map_maps_the_three_repos(self) -> None:
        m = migrate.load_map()
        self.assertEqual(m["repos"], {"psique": "self", "id-context": "id", "superego": "apparatus"})

    def test_plan_lists_pending_without_writing(self) -> None:
        kinds = sorted(c["kind"] for c in migrate.plan(json.loads(self.manifest.read_text()), self.home, MAP))
        self.assertEqual(kinds, ["file", "repo", "retired", "skill"])
        self.assertTrue((self.home / "rules" / "old-name.md").exists())

    def test_apply_renames_files_skills_and_imports_and_is_idempotent(self) -> None:
        done = migrate.apply(self.manifest, self.home, MAP, repos=False, prune=True)
        self.assertTrue((self.home / "rules" / "new-name.md").exists())
        self.assertFalse((self.home / "rules" / "old-name.md").exists())
        self.assertTrue((self.home / "skills" / "new-skill").is_dir())
        self.assertFalse((self.home / "rules" / "gone.md").exists())
        claude = (self.home / "CLAUDE.md").read_text(encoding="utf-8")
        self.assertIn("new-name.md", claude)
        self.assertIn("keep.md", claude)
        self.assertIn("old", json.loads(self.manifest.read_text())["layers"][0]["repo"])  # not without --repos
        self.assertTrue(done)
        self.assertEqual([d for d in migrate.apply(self.manifest, self.home, MAP, repos=False, prune=True) if not d.startswith("manifest")], [])

    def test_without_prune_a_retired_file_and_a_stale_duplicate_are_kept(self) -> None:
        (self.home / "rules" / "new-name.md").write_text("new\n", encoding="utf-8")  # the layer already shipped it
        done = migrate.apply(self.manifest, self.home, MAP, repos=False)
        self.assertTrue((self.home / "rules" / "old-name.md").exists())
        self.assertTrue((self.home / "rules" / "gone.md").exists())
        self.assertTrue(any(d.startswith("kept ") for d in done), done)
        migrate.apply(self.manifest, self.home, MAP, repos=False, prune=True)
        self.assertFalse((self.home / "rules" / "old-name.md").exists())
        self.assertFalse((self.home / "rules" / "gone.md").exists())

    def test_a_skill_that_belongs_to_the_person_is_left_alone(self) -> None:
        own = self.home / "skills" / "old-skill"
        (own / "SKILL.md").write_text("---\nlevel: ego\nname: old-skill\n---\nmine\n", encoding="utf-8")
        kinds = [c["kind"] for c in migrate.plan(json.loads(self.manifest.read_text()), self.home, MAP)]
        self.assertNotIn("skill", kinds)
        self.assertNotIn("stale", kinds)
        (own / "SKILL.md").write_text("---\nlevel: superego\nname: old-skill\n---\nshared\n", encoding="utf-8")
        kinds = [c["kind"] for c in migrate.plan(json.loads(self.manifest.read_text()), self.home, MAP)]
        self.assertIn("skill", kinds)

    def test_a_localized_alias_skill_is_not_stale(self) -> None:
        (self.home / "skills" / "new-skill").mkdir()
        (self.home / "skills" / "old-skill" / "SKILL.md").write_text(
            "---\nname: old-skill\n---\nFollow the canonical skill at [new-skill](../new-skill/SKILL.md).\n", encoding="utf-8")
        kinds = [c["kind"] for c in migrate.plan(json.loads(self.manifest.read_text()), self.home, MAP)]
        self.assertNotIn("stale", kinds)
        self.assertNotIn("skill", kinds)

    def test_a_retired_rule_listed_by_a_layer_of_the_person_is_kept(self) -> None:
        layer = Path(self.tmp.name) / "idlayer"
        layer.mkdir()
        (layer / "layer.json").write_text(json.dumps({"level": "id", "rules": ["gone.md"]}), encoding="utf-8")
        manifest = json.loads(self.manifest.read_text())
        manifest["layers"][1]["path"] = str(layer)
        retired = [c["old"] for c in migrate.plan(manifest, self.home, MAP) if c["kind"] == "retired"]
        self.assertEqual(retired, [])
        manifest["layers"][1]["level"] = "superego"  # a shared layer listing it does not count
        retired = [c["old"] for c in migrate.plan(manifest, self.home, MAP) if c["kind"] == "retired"]
        self.assertEqual(retired, ["rules/gone.md"])

    def test_repos_flag_rewrites_only_matching_urls(self) -> None:
        migrate.apply(self.manifest, self.home, MAP, repos=True)
        repos = [layer["repo"] for layer in json.loads(self.manifest.read_text())["layers"]]
        self.assertEqual(repos, ["git@github.com:acme/new.git", "git@github.com:acme/other.git"])

    def test_deprecated_prints_one_line(self) -> None:
        buf = io.StringIO()
        migrate.deprecated("a.py", "b.py", buf, "next major")
        self.assertEqual(buf.getvalue().count("\n"), 1)
        self.assertIn("b.py", buf.getvalue())

    def test_a_missing_manifest_prints_the_map_and_exits_clean(self) -> None:
        self.assertEqual(migrate.main(["--manifest", str(Path(self.tmp.name) / "none.json"), "--claude-home", str(self.home)]), 0)


if __name__ == "__main__":
    unittest.main()
