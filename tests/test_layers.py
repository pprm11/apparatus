"""Tests for tools/layers.py (routing by level) and tools/compose.py (root CLAUDE.md, index lines), plus the
layered restore.sh. No network, no real ~/.claude: everything lives in temp dirs."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import compose  # noqa: E402
import layers  # noqa: E402
from test_shell_sync import BASH, memory_text, posix, write  # noqa: E402


def skill_text(name: str, level: str = "") -> str:
    lvl = f"level: {level}\n" if level else ""
    return f"---\nname: {name}\ndescription: d\n{lvl}---\nbody\n"


class LayerSandbox(unittest.TestCase):
    """A fake ~/.claude plus three layer dirs and a manifest."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="cc-layers-")
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.home = os.path.join(self.tmp, "claude")
        self.dirs = {lvl: os.path.join(self.tmp, lvl) for lvl in ("superego", "ego", "id")}
        configs = {
            "superego": {"level": "superego", "globals": ["agent-rules.md"], "rules": ["map.md"],
                         "dirs": ["harness"], "files": []},
            "ego": {"level": "ego", "name": "test", "globals": ["glossary-test.md", "settings.json"],
                    "rules": [], "dirs": ["plans"], "files": []},
            "id": {"level": "id", "globals": ["patterns.md"], "rules": [], "dirs": [], "files": []},
        }
        for lvl, d in self.dirs.items():
            write(os.path.join(d, "layer.json"), json.dumps(configs[lvl]))
        self.manifest = os.path.join(self.tmp, "manifest.json")
        write(self.manifest, json.dumps({
            "default_level": "ego",
            "layers": [{"level": lvl, "path": posix(d), "active": True} for lvl, d in self.dirs.items()]}))
        self.man = layers.load_manifest(self.manifest)

    def memory(self, key, name, level="", body="body"):
        write(os.path.join(self.home, "projects", key, "memory", f"{name}.md"), memory_text(name, level, body))

    def exists(self, lvl, *rel):
        return os.path.exists(os.path.join(self.dirs[lvl], *rel))


class LayersPlanTest(LayerSandbox):
    def test_plan_routes_memories_and_skills_by_frontmatter(self):
        self.memory("p", "a", "superego")
        self.memory("p", "b", "id")
        self.memory("p", "c", "ego")
        self.memory("p", "d")  # no level: default
        self.memory("p", "e", "nonsense")  # unknown level: default
        write(os.path.join(self.home, "projects", "p", "memory", "MEMORY.md"), "- [a](a.md)\n")
        write(os.path.join(self.home, "skills", "s1", "SKILL.md"), skill_text("s1", "superego"))
        write(os.path.join(self.home, "skills", "s2", "SKILL.md"), skill_text("s2"))
        write(os.path.join(self.home, "skills", "synced", "SKILL.md"), skill_text("synced", "superego"))
        plan = layers.plan(self.man, self.home)
        dst = {lvl: sorted(d for _, d in items) for lvl, items in plan.items()}
        self.assertEqual(dst["superego"], ["memory/p/MEMORY.md", "memory/p/a.md", "skills/s1"])
        self.assertEqual(dst["id"], ["memory/p/MEMORY.md", "memory/p/b.md"])
        self.assertEqual(dst["ego"], ["memory/p/MEMORY.md", "memory/p/c.md", "memory/p/d.md", "memory/p/e.md",
                                      "skills/s2"])

    def test_default_level_comes_from_the_manifest(self):
        self.memory("p", "d")
        man = dict(self.man, default_level="id")
        plan = layers.plan(man, self.home)
        self.assertEqual([d for _, d in plan["id"]], ["memory/p/d.md"])
        self.assertEqual(plan["ego"], [])

    def test_unlabeled_lists_memories_and_skills_without_level(self):
        self.memory("p", "a", "ego")
        self.memory("p", "b")
        write(os.path.join(self.home, "projects", "p", "memory", "MEMORY.md"), "- [b](b.md)\n")
        write(os.path.join(self.home, "skills", "s1", "SKILL.md"), skill_text("s1"))
        write(os.path.join(self.home, "skills", "s2", "SKILL.md"), skill_text("s2", "id"))
        write(os.path.join(self.home, "skills", "synced", "SKILL.md"), skill_text("synced"))
        self.assertEqual(layers.unlabeled(self.home), ["skills/s1", "projects/p/memory/b.md"])

    def test_frontmatter_level_only_reads_the_first_block(self):
        p = os.path.join(self.tmp, "f.md")
        write(p, "---\nname: x\n---\nlevel: id\n")
        self.assertIsNone(layers.frontmatter_level(p))
        write(p, "no frontmatter\nlevel: id\n")
        self.assertIsNone(layers.frontmatter_level(p))

    def test_index_is_filtered_per_level_so_no_link_dangles(self):
        self.memory("p", "mine", "ego")
        self.memory("p", "theirs", "id")
        idx = os.path.join(self.home, "projects", "p", "memory", "MEMORY.md")
        write(idx, "# Memory\n- [mine](mine.md) - m\n- [theirs](theirs.md) - t\n- [elsewhere](gone.md) - g\n")
        self.assertEqual(layers.filter_index(idx, "ego", "ego"),
                         "# Memory\n- [mine](mine.md) - m\n- [elsewhere](gone.md) - g\n")
        self.assertEqual(layers.filter_index(idx, "id", "ego"),
                         "# Memory\n- [theirs](theirs.md) - t\n- [elsewhere](gone.md) - g\n")

    def test_frontmatter_level_reads_a_level_indented_under_metadata(self):
        p = os.path.join(self.tmp, "m.md")
        write(p, "---\nname: x\nmetadata:\n  type: project\n  level: id\n  keywords: a, b\n---\nbody\n")
        self.assertEqual(layers.frontmatter_level(p), "id")
        write(p, "---\nname: x\nmetadata:\n  level: bogus\n---\n")
        self.assertIsNone(layers.frontmatter_level(p))


class LayersExportTest(LayerSandbox):
    def test_export_writes_each_layer_from_its_config_and_level(self):
        self.memory("p", "a", "superego")
        self.memory("p", "b")
        write(os.path.join(self.home, "agent-rules.md"), "general\n")
        write(os.path.join(self.home, "glossary-test.md"), "glossary\n")
        write(os.path.join(self.home, "rules", "map.md"), "map\n")
        write(os.path.join(self.home, "harness", "claude.md"), "adapter\n")
        write(os.path.join(self.home, "plans", "plan.md"), "plan\n")
        for lvl in ("superego", "ego", "id"):
            layers.export(self.man, self.home, lvl)
        self.assertTrue(self.exists("superego", "memory", "p", "a.md"))
        self.assertTrue(self.exists("superego", "global", "agent-rules.md"))
        self.assertTrue(self.exists("superego", "rules", "map.md"))
        self.assertTrue(self.exists("superego", "harness", "claude.md"))
        self.assertTrue(self.exists("ego", "memory", "p", "b.md"))
        self.assertTrue(self.exists("ego", "global", "glossary-test.md"))
        self.assertTrue(self.exists("ego", "plans", "plan.md"))
        self.assertFalse(self.exists("ego", "memory", "p", "a.md"))
        self.assertFalse(self.exists("id", "memory"))

    def test_changing_the_level_moves_the_file_to_the_other_repo(self):
        self.memory("p", "a", "ego")
        layers.export(self.man, self.home, "ego")
        layers.export(self.man, self.home, "id")
        self.assertTrue(self.exists("ego", "memory", "p", "a.md"))
        self.memory("p", "a", "id")
        layers.export(self.man, self.home, "ego")
        layers.export(self.man, self.home, "id")
        self.assertFalse(self.exists("ego", "memory", "p", "a.md"))
        self.assertTrue(self.exists("id", "memory", "p", "a.md"))
        with open(os.path.join(self.dirs["id"], "memory", "p", "a.md"), encoding="utf-8") as fh:
            self.assertIn("level: id", fh.read())

    def test_prune_leaves_the_repos_own_files_alone(self):
        ego = self.dirs["ego"]
        for rel in ("README.md", ".gitignore", os.path.join("tools", "x.py"), os.path.join("tests", "t.py"),
                    os.path.join("reports", "2026-10-26.md"), "log.md"):
            write(os.path.join(ego, rel), "own\n")
        write(os.path.join(ego, "memory", "p", "stale.md"), "stale\n")
        write(os.path.join(ego, "global", "old.md"), "old\n")
        write(os.path.join(ego, "plans", "gone.md"), "gone\n")
        layers.export(self.man, self.home, "ego")
        for rel in ("layer.json", "README.md", ".gitignore", os.path.join("tools", "x.py"),
                    os.path.join("tests", "t.py"), os.path.join("reports", "2026-10-26.md"), "log.md"):
            self.assertTrue(self.exists("ego", rel), rel)
        self.assertFalse(self.exists("ego", "memory", "p", "stale.md"))
        self.assertFalse(self.exists("ego", "global", "old.md"))
        self.assertFalse(self.exists("ego", "plans", "gone.md"))
        self.assertFalse(self.exists("ego", "memory"), "emptied folders are removed")

    def test_dry_run_changes_nothing(self):
        self.memory("p", "a")
        log = layers.export(self.man, self.home, "ego", dry=True)
        self.assertTrue(any("memory/p/a.md" in line.replace(os.sep, "/") for line in log), log)
        self.assertFalse(self.exists("ego", "memory"))

    def test_inactive_or_unknown_level_is_an_error(self):
        self.man["layers"][2]["active"] = False
        with self.assertRaises(SystemExit):
            layers.export(self.man, self.home, "id")

    def test_cli_plan_and_unlabeled(self):
        self.memory("p", "a")
        base = [sys.executable, "-I", os.path.join(ROOT, "tools", "layers.py")]
        args = ["--manifest", self.manifest, "--claude-home", self.home]
        plan = subprocess.run([*base, "plan", *args], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(plan.returncode, 0, plan.stderr)
        self.assertIn("ego\tprojects/p/memory/a.md\tmemory/p/a.md", plan.stdout)
        unl = subprocess.run([*base, "unlabeled", *args], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(unl.stdout.split(), ["projects/p/memory/a.md"])


class ComposeTest(LayerSandbox):
    def test_root_claude_md_lists_each_layers_md_globals_in_manifest_order(self):
        for name in ("agent-rules.md", "glossary-test.md", "settings.json", "patterns.md"):
            write(os.path.join(self.home, name), "x\n")
        text = compose.root_claude_md(self.man, self.home)
        order = [text.index(s) for s in ("## General rules (superego)", "@~/.claude/agent-rules.md",
                                         "## Company (ego)", "@~/.claude/glossary-test.md",
                                         "## User (id)", "@~/.claude/patterns.md", "@~/.claude/harness/claude.md")]
        self.assertEqual(order, sorted(order))
        self.assertNotIn("settings.json", text)  # only .md globals are imported

    def test_layer_without_present_globals_gets_no_section(self):
        write(os.path.join(self.home, "patterns.md"), "x\n")
        text = compose.root_claude_md(self.man, self.home)
        self.assertNotIn("## General rules (superego)", text)
        self.assertNotIn("## Company (ego)", text)
        self.assertIn("## User (id)", text)

    def test_inactive_layer_is_left_out(self):
        write(os.path.join(self.home, "glossary-test.md"), "x\n")
        self.man["layers"][1]["active"] = False
        self.assertNotIn("glossary-test.md", compose.root_claude_md(self.man, self.home))

    def test_missing_index_lines_are_found_and_listed_ones_are_not(self):
        self.memory("p", "listed")
        self.memory("p", "unlisted", body="b")
        write(os.path.join(self.home, "projects", "p", "memory", "MEMORY.md"), "# Memory\n\n- [listed](listed.md) — d\n")
        out = compose.missing_index_lines(self.home)
        idx = os.path.join(self.home, "projects", "p", "memory", "MEMORY.md")
        self.assertEqual(list(out), [idx])
        self.assertEqual(len(out[idx]), 1)
        self.assertTrue(out[idx][0].startswith("- [unlisted](unlisted.md)"), out[idx])

    def test_main_appends_index_lines_and_writes_claude_md(self):
        self.memory("p", "unlisted")
        write(os.path.join(self.home, "patterns.md"), "x\n")
        codex = os.path.join(self.tmp, "codex")
        base = [sys.executable, "-I", os.path.join(ROOT, "tools", "compose.py"), "--manifest", self.manifest,
                "--claude-home", self.home, "--codex-home", codex]
        r = subprocess.run(base, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        with open(os.path.join(self.home, "projects", "p", "memory", "MEMORY.md"), encoding="utf-8") as fh:
            self.assertIn("(unlisted.md)", fh.read())
        with open(os.path.join(self.home, "CLAUDE.md"), encoding="utf-8") as fh:
            self.assertIn("@~/.claude/patterns.md", fh.read())
        again = subprocess.run(base, capture_output=True, text=True, encoding="utf-8")
        self.assertNotIn("index ", again.stdout)  # second run adds no index lines


@unittest.skipUnless(BASH and shutil.which("git"), "needs Git Bash and git")
class RestoreFromLayerTest(LayerSandbox):
    def test_restore_from_a_layer_copies_its_files_into_claude_home(self):
        ego = self.dirs["ego"]
        write(os.path.join(ego, "global", "glossary-test.md"), "glossary\n")
        write(os.path.join(ego, "skills", "s", "SKILL.md"), skill_text("s"))
        write(os.path.join(ego, "memory", "p", "a.md"), memory_text("a"))
        write(os.path.join(ego, "plans", "plan.md"), "plan\n")
        shutil.copy(os.path.join(ROOT, "restore.sh"), os.path.join(self.tmp, "restore.sh"))
        shutil.copy(os.path.join(ROOT, "lib.sh"), os.path.join(self.tmp, "lib.sh"))
        os.makedirs(os.path.join(self.tmp, "tools"))
        for f in os.listdir(os.path.join(ROOT, "tools")):
            if f.endswith(".py"):
                shutil.copy(os.path.join(ROOT, "tools", f), os.path.join(self.tmp, "tools", f))
        target = os.path.join(self.tmp, "restored")
        env = dict(os.environ, HOME=os.path.join(self.tmp, "h"), USERPROFILE=os.path.join(self.tmp, "h"),
                   PYTHONIOENCODING="utf-8")
        r = subprocess.run([BASH, posix(os.path.join(self.tmp, "restore.sh")), "--from", posix(ego),
                            "--claude-home", posix(target)], capture_output=True, text=True, encoding="utf-8",
                           env=env, timeout=120)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertTrue(os.path.isfile(os.path.join(target, "glossary-test.md")))
        self.assertTrue(os.path.isfile(os.path.join(target, "skills", "s", "SKILL.md")))
        self.assertTrue(os.path.isfile(os.path.join(target, "projects", "p", "memory", "a.md")))
        self.assertTrue(os.path.isfile(os.path.join(target, "plans", "plan.md")))  # dirs of layer.json
        bad = subprocess.run([BASH, posix(os.path.join(self.tmp, "restore.sh")), "--from", posix(self.dirs["ego"] + "-nope"),
                              "--claude-home", posix(target)], capture_output=True, text=True, encoding="utf-8", env=env)
        self.assertNotEqual(bad.returncode, 0)


class ReadonlyLayerTest(LayerSandbox):
    """The shared collective layer: composed and restored like any layer, never exported into or pushed."""

    def setUp(self):
        super().setUp()
        coll = os.path.join(self.tmp, "collective")
        self.dirs["collective"] = coll
        write(os.path.join(coll, "layer.json"), json.dumps({
            "level": "collective", "mode": "readonly", "globals": ["collective-glossary.md"],
            "rules": ["collective-engineering.md"], "dirs": [], "files": []}))
        entry = {"level": "collective", "path": posix(coll), "active": True, "mode": "readonly"}
        man = layers.read_json(self.manifest)
        man["layers"].insert(1, entry)  # superego, collective, ego, id
        write(self.manifest, json.dumps(man))
        self.man = layers.load_manifest(self.manifest)

    def test_compose_puts_the_collective_between_superego_and_ego(self):
        write(os.path.join(self.home, "agent-rules.md"), "r\n")
        write(os.path.join(self.home, "collective-glossary.md"), "c\n")
        write(os.path.join(self.home, "glossary-test.md"), "g\n")
        text = compose.root_claude_md(self.man, self.home)
        self.assertLess(text.index("agent-rules.md"), text.index("collective-glossary.md"))
        self.assertLess(text.index("collective-glossary.md"), text.index("glossary-test.md"))
        self.assertIn("## Team (collective)", text)

    def test_export_all_skips_the_readonly_layer_and_never_writes_into_it(self):
        write(os.path.join(self.home, "collective-glossary.md"), "edited locally\n")
        write(os.path.join(self.dirs["collective"], "global", "collective-glossary.md"), "shared\n")
        write(os.path.join(self.dirs["collective"], "skills", "collective-x", "SKILL.md"), skill_text("collective-x", "collective"))
        self.assertEqual([l["level"] for l in layers.writable_layers(self.man)], ["superego", "ego", "id"])
        with self.assertRaises(SystemExit):
            layers.export(self.man, self.home, "collective")
        for lvl in ("superego", "ego", "id"):
            layers.export(self.man, self.home, lvl)
        with open(os.path.join(self.dirs["collective"], "global", "collective-glossary.md"), encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "shared\n")
        self.assertTrue(self.exists("collective", "skills", "collective-x", "SKILL.md"))

    def test_a_restored_collective_skill_is_not_routed_to_the_ego_repo(self):
        write(os.path.join(self.home, "skills", "collective-x", "SKILL.md"), skill_text("collective-x", "collective"))
        self.assertEqual(layers.frontmatter_level(os.path.join(self.home, "skills", "collective-x", "SKILL.md")), "collective")
        layers.export(self.man, self.home, "ego")
        self.assertFalse(self.exists("ego", "skills", "collective-x"))

    def test_pull_without_a_remote_does_nothing(self):
        subprocess.run(["git", "init", "-q", self.dirs["collective"]], check=True)
        self.assertEqual(layers.pull(self.man), ["[collective] no remote, nothing to pull"])


class SealedPathsTest(LayerSandbox):
    """Paths listed under `sealed` in layer.json never reach the repo in plain text."""

    def setUp(self):
        super().setUp()
        with open(os.path.join(self.dirs["id"], "layer.json"), encoding="utf-8") as fh:
            cfg = json.load(fh)
        cfg["dirs"] = ["notes"]
        cfg["sealed"] = ["pdi", "notes/private", "projects/P/memory/secret.md"]
        write(os.path.join(self.dirs["id"], "layer.json"), json.dumps(cfg))
        self.man = layers.load_manifest(self.manifest)
        write(os.path.join(self.home, "pdi", "pdi.md"), "plan")
        write(os.path.join(self.home, "pdi", "evidencias", "d", "x.md"), "evidence")
        write(os.path.join(self.home, "notes", "ok.md"), "ok")
        write(os.path.join(self.home, "notes", "private", "no.md"), "no")
        self.memory("P", "secret", "id")
        self.memory("P", "open", "id")

    def test_export_skips_sealed_dirs_files_and_memories(self):
        layers.export(self.man, self.home, "id")
        self.assertFalse(self.exists("id", "pdi"))
        self.assertTrue(self.exists("id", "notes", "ok.md"))
        self.assertFalse(self.exists("id", "notes", "private"))
        self.assertTrue(self.exists("id", "memory", "P", "open.md"))
        self.assertFalse(self.exists("id", "memory", "P", "secret.md"))

    def test_a_plaintext_copy_already_in_the_repo_is_pruned(self):
        write(os.path.join(self.dirs["id"], "memory", "P", "secret.md"), "leaked")
        layers.export(self.man, self.home, "id")
        self.assertFalse(self.exists("id", "memory", "P", "secret.md"))

    def test_the_index_does_not_list_a_path_sealed_memory(self):
        write(os.path.join(self.home, "projects", "P", "memory", "MEMORY.md"),
              "- [Open note](open.md) — public hook\n- [Private diagnosis](secret.md) — private hook\n")
        layers.export(self.man, self.home, "id")
        with open(os.path.join(self.dirs["id"], "memory", "P", "MEMORY.md"), encoding="utf-8") as fh:
            index = fh.read()
        self.assertIn("open.md", index)
        self.assertNotIn("secret", index)
        self.assertNotIn("private hook", index)

    def test_a_flagged_markdown_inside_a_mirrored_dir_is_withheld(self):
        write(os.path.join(self.home, "notes", "flagged.md"), "---\nsealed: true\n---\nx\n")
        layers.export(self.man, self.home, "id")
        self.assertTrue(self.exists("id", "notes", "ok.md"))
        self.assertFalse(self.exists("id", "notes", "flagged.md"))

    def test_is_sealed_matches_the_path_and_its_children_only(self):
        sealed = layers.sealed_paths({"sealed": ["pdi", "a/b.md"]})
        self.assertTrue(layers.is_sealed("pdi", sealed))
        self.assertTrue(layers.is_sealed("pdi/x/y.md", sealed))
        self.assertTrue(layers.is_sealed("a/b.md", sealed))
        self.assertFalse(layers.is_sealed("pdi-notes/x.md", sealed))
        self.assertFalse(layers.is_sealed("a/b.md.bak", sealed))


class InboxRoutingTest(LayerSandbox):
    """The live decision inbox goes whole to the layer flagged "inbox": true and to no other."""

    def setUp(self):
        super().setUp()
        with open(os.path.join(self.dirs["id"], "layer.json"), encoding="utf-8") as fh:
            cfg = json.load(fh)
        cfg["inbox"] = True
        write(os.path.join(self.dirs["id"], "layer.json"), json.dumps(cfg))
        self.man = layers.load_manifest(self.manifest)
        write(os.path.join(self.home, "decisions", "inbox.json"), json.dumps({"next": 3, "items": [
            {"id": "D-1", "level": "superego"}, {"id": "D-2", "level": "id"}]}))

    def test_whole_inbox_lands_in_the_flagged_layer_only(self):
        write(os.path.join(self.dirs["superego"], "decisions", "inbox.json"), "{}")  # an old subset copy
        for lvl in ("superego", "ego", "id"):
            layers.export(self.man, self.home, lvl)
        self.assertFalse(self.exists("superego", "decisions", "inbox.json"))
        self.assertFalse(self.exists("ego", "decisions", "inbox.json"))
        with open(os.path.join(self.dirs["id"], "decisions", "inbox.json"), encoding="utf-8") as fh:
            self.assertEqual(len(json.load(fh)["items"]), 2)

    def test_export_log_does_not_depend_on_the_cwd(self):
        old = os.getcwd()
        os.chdir(self.tmp)
        try:
            log = layers.export(self.man, self.home, "id")
        finally:
            os.chdir(old)
        self.assertTrue(any(line.startswith("copy ") for line in log))


class SealedFlagTest(LayerSandbox):
    """A memory or skill whose frontmatter says `sealed: true` never reaches a repo in plain text, under any
    project key. layer.json names a fixed key; a repo move renames the key and the entry stops matching, so the
    flag travels with the file instead."""

    def flagged(self, key, name, text):
        p = os.path.join(self.home, "projects", key, "memory", f"{name}.md")
        write(p, text)
        return p

    def test_a_flagged_memory_is_skipped_under_any_project_key(self):
        for key in ("P", "P-moved"):
            self.flagged(key, "me", "---\nlevel: id\nsealed: true\nname: me\ndescription: d\n---\nbody\n")
            self.flagged(key, "nested",
                         "---\nname: nested\ndescription: d\nmetadata:\n  level: id\n  sealed: true\n---\nbody\n")
            self.flagged(key, "plain",
                         "---\nlevel: id\nname: plain\ndescription: d\nsealed: false\n---\nsealed: true in the body\n")
        log = layers.export(self.man, self.home, "id")
        for key in ("P", "P-moved"):
            self.assertFalse(self.exists("id", "memory", key, "me.md"))
            self.assertFalse(self.exists("id", "memory", key, "nested.md"))
            self.assertTrue(self.exists("id", "memory", key, "plain.md"))
        self.assertTrue(any("withheld" in ln and "me.md" in ln for ln in log), log)

    def test_a_flagged_memory_already_in_the_repo_is_pruned(self):
        self.flagged("P", "me", "---\nlevel: id\nsealed: true\n---\nx\n")
        write(os.path.join(self.dirs["id"], "memory", "P", "me.md"), "leaked")
        layers.export(self.man, self.home, "id")
        self.assertFalse(self.exists("id", "memory", "P", "me.md"))

    def test_the_index_does_not_list_a_flagged_memory(self):
        self.flagged("P", "me", "---\nlevel: id\nsealed: true\n---\nx\n")
        self.memory("P", "open", "id")
        write(os.path.join(self.home, "projects", "P", "memory", "MEMORY.md"),
              "# Memory\n- [Open note](open.md) — public hook\n- [Private diagnosis](me.md) — private hook\n")
        layers.export(self.man, self.home, "id")
        with open(os.path.join(self.dirs["id"], "memory", "P", "MEMORY.md"), encoding="utf-8") as fh:
            index = fh.read()
        self.assertIn("open.md", index)
        self.assertNotIn("me.md", index)
        self.assertNotIn("Private diagnosis", index)
        self.assertNotIn("private hook", index)

    def test_a_key_whose_only_memories_are_flagged_gets_no_index_in_the_repo(self):
        # Without a level the flagged memory falls to the default layer (the shared ego): nothing of it may land there.
        self.flagged("Q", "me", "---\nsealed: true\n---\nx\n")
        index = "# Memory\n- [Private](me.md) — hook\n"
        write(os.path.join(self.home, "projects", "Q", "memory", "MEMORY.md"), index)
        write(os.path.join(self.dirs["ego"], "memory", "Q", "MEMORY.md"), index)
        layers.export(self.man, self.home, "ego")
        self.assertFalse(self.exists("ego", "memory", "Q"))

    def test_a_flagged_skill_is_withheld(self):
        write(os.path.join(self.home, "skills", "private-skill", "SKILL.md"),
              "---\nname: private-skill\ndescription: d\nlevel: id\nsealed: true\n---\nbody\n")
        write(os.path.join(self.home, "skills", "open-skill", "SKILL.md"), skill_text("open-skill", "id"))
        layers.export(self.man, self.home, "id")
        self.assertTrue(self.exists("id", "skills", "open-skill", "SKILL.md"))
        self.assertFalse(self.exists("id", "skills", "private-skill"))

    def test_the_flag_fails_closed_on_every_spelling_a_person_might_use(self):
        os.makedirs(self.home, exist_ok=True)
        p = os.path.join(self.home, "x.md")
        for text in (
            "---\nname: x\nsealed: true\n---\nbody\n",
            "\ufeff---\nname: x\nsealed: true\n---\nbody\n",  # UTF-8 BOM from a Windows editor
            "\n---\nname: x\nsealed: true\n---\nbody\n",                 # blank line before the block
            "---\nname: x\nsealed: True\n---\nbody\n",
            "---\nname: x\nsealed: YES\n---\nbody\n",
            "---\nname: x\nsealed: \"true\"\n---\nbody\n",
            "---\nname: x\nsealed: 'true'\n---\nbody\n",
            "---\nname: x\nsealed: true  # private\n---\nbody\n",
            "---\nname: x\nsealed: anything-else\n---\nbody\n",           # a value that is not a clear no is a yes
            "---\nname: x\ndescription: " + "d" * 5000 + "\nsealed: true\n---\nbody\n",  # past the old 4 KB read
            "---\r\nname: x\r\nsealed: true\r\n---\r\nbody\r\n",
        ):
            with open(p, "w", encoding="utf-8", newline="") as fh:
                fh.write(text)
            self.assertTrue(layers.frontmatter_sealed(p), repr(text[:60]))

    def test_the_flag_is_off_only_on_an_explicit_no_or_outside_the_block(self):
        p = os.path.join(self.home, "x.md")
        for text in (
            "---\nname: x\n---\nsealed: true\n",                          # body, not frontmatter
            "no frontmatter\nsealed: true\n",
            "---\nname: x\nsealed: false\n---\nbody\n",
            "---\nname: x\nsealed: no\n---\nbody\n",
            "---\nname: x\nsealed: 0\n---\nbody\n",
            "---\nname: x\nsealed:\n---\nbody\n",
            "---\nname: x\ndescription: sealed stuff\n---\nbody\n",
        ):
            write(p, text)
            self.assertFalse(layers.frontmatter_sealed(p), repr(text[:60]))
        self.assertFalse(layers.frontmatter_sealed(os.path.join(self.home, "missing.md")))


if __name__ == "__main__":
    unittest.main()
