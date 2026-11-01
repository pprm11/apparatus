"""compose.py / render_harness.py --company: one company's home from fictional layer repos (offline)."""
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, os.path.join(ROOT, "tools"))
import compose  # noqa: E402
import layers  # noqa: E402
import render_harness  # noqa: E402

# Fictional company terms. They identify a company; none may reach the other company home.
ALPHA, BETA = "zorbex", "quillon"


def write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


class CompanySandbox(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = os.path.realpath(self._tmp.name)
        self.codes = os.path.join(self.tmp, "Codes")
        layer_specs = {
            "superego": ("superego", {"globals": ["rules-general.md"], "rules": ["r-general.md"]}),
            "id": ("id", {"globals": ["me.md", "settings.json"], "rules": []}),
            "ego-alpha": ("ego", {"globals": ["glossary-alpha.md"], "rules": [], "company": "alpha"}),
            "ego-beta": ("ego", {"globals": ["glossary-beta.md"], "rules": ["r-beta.md"], "company": "beta"}),
            "collective-alpha": ("collective", {"globals": ["glossary.md"], "rules": ["r-collective.md"]}),
        }
        body = {"rules-general.md": "general rules", "me.md": "personal preferences", "settings.json": "{}",
                "glossary-alpha.md": f"{ALPHA} glossary", "glossary-beta.md": f"{BETA} glossary",
                "r-general.md": "general rule", "r-beta.md": f"{BETA} rule", "glossary.md": f"{ALPHA} collective",
                "r-collective.md": f"{ALPHA} collective rule"}
        for name, (level, cfg) in layer_specs.items():
            root = os.path.join(self.codes, name)
            write(os.path.join(root, "layer.json"), json.dumps({"level": level, **cfg}))
            for f in cfg["globals"]:
                write(os.path.join(root, "global", f), body[f] + "\n")
            for f in cfg["rules"]:
                write(os.path.join(root, "rules", f), body[f] + "\n")
        write(os.path.join(self.codes, "superego", "harness", "claude.md"), "CLAUDE ADAPTER\n")
        write(os.path.join(self.codes, "superego", "harness", "codex.md"), "CODEX ADAPTER\n")
        self.manifest = os.path.join(self.tmp, "manifest.json")
        write(self.manifest, json.dumps({
            "default_level": "ego",
            "layers": [
                {"level": "superego", "path": os.path.join(self.codes, "superego"), "repo": "x", "active": True},
                {"level": "ego", "name": "alpha", "company": "alpha", "path": os.path.join(self.codes, "ego-alpha"),
                 "repo": "x", "active": True},
                {"level": "id", "path": os.path.join(self.codes, "id"), "repo": "x", "active": True},
                {"level": "ego", "name": "beta", "company": "beta", "path": os.path.join(self.codes, "ego-beta"),
                 "repo": "x", "active": False},
            ],
            "budgets": {"superego": 1000, "collective": 1000, "ego": 1000, "id": 1000, "adapter": 1000, "root": 2000},
        }))
        self.companies = os.path.join(self.tmp, "companies.json")
        write(self.companies, json.dumps({"companies": {
            "alpha": {"ego": "ego-alpha", "collective": "collective-alpha", "prefixes": [], "home": {}},
            "beta": {"ego": "ego-beta", "collective": "collective-beta", "prefixes": [], "home": {}},
        }}))

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def cli(self, *args: str) -> subprocess.CompletedProcess:
        cmd = [sys.executable, "-I", os.path.join(ROOT, "tools", "compose.py"), "--manifest", self.manifest,
               "--companies", self.companies, "--codes", self.codes, *args]
        return subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")

    def tree_text(self, out: str) -> str:
        parts = []
        for root, _, names in os.walk(out):
            for n in names:
                with open(os.path.join(root, n), encoding="utf-8") as fh:
                    parts.append(fh.read())
        return "\n".join(parts).lower()


class ComposeCompanyTest(CompanySandbox):
    def test_each_home_has_only_its_own_company_and_the_shared_layers(self) -> None:
        for mine, theirs in ((ALPHA, BETA), (BETA, ALPHA)):
            company = "alpha" if mine == ALPHA else "beta"
            out = os.path.join(self.tmp, "out-" + company)
            r = self.cli("--company", company, "--out", out)
            self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
            text = self.tree_text(out)
            self.assertIn(mine, text)
            self.assertEqual(text.count(theirs), 0, f"{theirs} leaked into the {company} home")
            for shared in ("general rules", "personal preferences"):
                self.assertIn(shared, text)
            for name in ("CLAUDE.md", "AGENTS.md"):
                self.assertTrue(os.path.isfile(os.path.join(out, name)), name)

    def test_inactive_ego_of_the_company_is_used_and_collective_comes_from_companies_json(self) -> None:
        out = os.path.join(self.tmp, "out-beta")
        self.assertEqual(self.cli("--company", "beta", "--out", out).returncode, 0)  # ego-beta is active: false
        self.assertIn(BETA, self.tree_text(out))
        out_a = os.path.join(self.tmp, "out-alpha")
        self.assertEqual(self.cli("--company", "alpha", "--out", out_a).returncode, 0)
        self.assertIn(f"{ALPHA} collective rule", self.tree_text(out_a))  # collective-alpha is not in the manifest

    def test_claude_md_imports_are_relative_and_agents_md_inlines_them(self) -> None:
        out = os.path.join(self.tmp, "out")
        self.assertEqual(self.cli("--company", "alpha", "--out", out).returncode, 0)
        with open(os.path.join(out, "CLAUDE.md"), encoding="utf-8") as fh:
            claude = fh.read()
        self.assertNotIn("~/.claude", claude)  # a company home never points at the personal home
        self.assertIn("@./global/rules-general.md", claude)
        self.assertIn("@./harness/claude.md", claude)
        order = [claude.index(s) for s in ("(superego)", "(collective)", "(ego)", "(id)")]
        self.assertEqual(order, sorted(order))
        self.assertNotIn("settings.json", claude)
        with open(os.path.join(out, "AGENTS.md"), encoding="utf-8") as fh:
            agents = fh.read()
        for part in ("general rules", "personal preferences", f"{ALPHA} glossary", "CODEX ADAPTER", "general rule"):
            self.assertIn(part, agents)
        self.assertNotIn("CLAUDE ADAPTER", agents)
        self.assertNotRegex(agents, r"(?m)^@")

    def test_ego_without_company_is_never_read(self) -> None:
        with open(self.manifest, encoding="utf-8") as fh:
            man = json.load(fh)
        del man["layers"][1]["company"]
        write(self.manifest, json.dumps(man))
        out = os.path.join(self.tmp, "out")
        r = self.cli("--company", "alpha", "--out", out)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotIn(f"{ALPHA} glossary", self.tree_text(out))
        self.assertIn("skip ego layer alpha", r.stderr)

    def test_skills_of_ego_and_collective_are_copied_and_only_of_that_company(self) -> None:
        for layer, skill in (("ego-alpha", "sk-alpha"), ("collective-alpha", "sk-coll"), ("ego-beta", "sk-beta"),
                             ("superego", "sk-shared")):
            write(os.path.join(self.codes, layer, "skills", skill, "SKILL.md"), f"{skill} body\n")
            write(os.path.join(self.codes, layer, "skills", skill, "ref", "r.md"), "ref\n")
        out = os.path.join(self.tmp, "out")
        write(os.path.join(out, "skills", "stale", "SKILL.md"), f"{BETA}\n")
        self.assertEqual(self.cli("--company", "alpha", "--out", out).returncode, 0)
        self.assertEqual(sorted(os.listdir(os.path.join(out, "skills"))), ["sk-alpha", "sk-coll"])
        self.assertTrue(os.path.isfile(os.path.join(out, "skills", "sk-coll", "ref", "r.md")))
        self.assertEqual(self.tree_text(out).count(BETA), 0)

    def test_same_skill_in_two_layers_is_refused(self) -> None:
        for layer in ("ego-alpha", "collective-alpha"):
            write(os.path.join(self.codes, layer, "skills", "dup", "SKILL.md"), "x\n")
        r = self.cli("--company", "alpha", "--out", os.path.join(self.tmp, "out"))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("skill dup exists in two layers", r.stderr)

    def test_unknown_company_fails_and_writes_nothing(self) -> None:
        out = os.path.join(self.tmp, "out")
        r = self.cli("--company", "gamma", "--out", out)
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("unknown company", r.stderr)
        self.assertFalse(os.path.exists(out))

    def test_company_needs_out(self) -> None:
        self.assertNotEqual(self.cli("--company", "alpha").returncode, 0)

    def test_over_budget_refuses_to_write(self) -> None:
        with open(self.manifest, encoding="utf-8") as fh:
            man = json.load(fh)
        man["budgets"]["ego"] = 5
        write(self.manifest, json.dumps(man))
        out = os.path.join(self.tmp, "out")
        r = self.cli("--company", "alpha", "--out", out)
        self.assertEqual(r.returncode, 1)
        self.assertIn("over its budget", r.stderr)
        self.assertFalse(os.path.exists(out))

    def test_dry_run_writes_nothing_and_a_rerun_drops_stale_files(self) -> None:
        out = os.path.join(self.tmp, "out")
        self.assertEqual(self.cli("--company", "alpha", "--out", out, "--dry-run").returncode, 0)
        self.assertFalse(os.path.exists(out))
        write(os.path.join(out, "rules", "left-over.md"), f"{BETA} stale\n")
        self.assertEqual(self.cli("--company", "alpha", "--out", out).returncode, 0)
        self.assertFalse(os.path.exists(os.path.join(out, "rules", "left-over.md")))

    def test_same_file_name_in_two_layers_is_refused(self) -> None:
        write(os.path.join(self.codes, "ego-alpha", "global", "me.md"), "dup\n")
        cfg = os.path.join(self.codes, "ego-alpha", "layer.json")
        with open(cfg, encoding="utf-8") as fh:
            data = json.load(fh)
        data["globals"].append("me.md")
        write(cfg, json.dumps(data))
        r = self.cli("--company", "alpha", "--out", os.path.join(self.tmp, "out"))
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("exists in two layers", r.stderr)


class RenderCompanyTest(CompanySandbox):
    def run_render(self, *extra: str) -> tuple[int, str]:
        out = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
        argv = ["x", "--manifest", self.manifest, "--companies", self.companies, "--codes", self.codes, *extra]
        with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = render_harness.main()
        out.flush()
        return code, out.buffer.getvalue().decode("utf-8")

    def test_writes_only_agents_md_with_the_company_layers(self) -> None:
        codex = os.path.join(self.tmp, "codex-alpha")
        os.makedirs(codex)
        code, text = self.run_render("--company", "alpha", "--codex-home", codex)
        self.assertEqual(code, 0, text)
        self.assertEqual(os.listdir(codex), ["AGENTS.md"])  # no skills folder, nothing else
        with open(os.path.join(codex, "AGENTS.md"), encoding="utf-8") as fh:
            agents = fh.read().lower()
        self.assertIn(ALPHA, agents)
        self.assertEqual(agents.count(BETA), 0)

    def test_missing_codex_home_is_not_created(self) -> None:
        codex = os.path.join(self.tmp, "absent")
        code, text = self.run_render("--company", "alpha", "--codex-home", codex)
        self.assertEqual(code, 0)
        self.assertIn("no Codex home", text)
        self.assertFalse(os.path.exists(codex))

    def test_codex_home_defaults_to_the_company_home_in_companies_json(self) -> None:
        home = os.path.join(self.tmp, "homes", "alpha", "codex")
        os.makedirs(home)
        with open(self.companies, encoding="utf-8") as fh:
            data = json.load(fh)
        data["companies"]["alpha"]["home"] = {"codex": home}
        write(self.companies, json.dumps(data))
        self.assertEqual(self.run_render("--company", "alpha")[0], 0)
        self.assertTrue(os.path.isfile(os.path.join(home, "AGENTS.md")))
        self.assertEqual(self.run_render("--company", "beta")[0], 1)  # beta declares no home.codex

    def test_codex_skills_are_portable_only_and_codex_own_skills_survive(self) -> None:
        write(os.path.join(self.codes, "superego", "harness", "skills.json"), '{"claude_only": ["sk-claude"]}')
        for skill in ("sk-alpha", "sk-claude"):
            write(os.path.join(self.codes, "ego-alpha", "skills", skill, "SKILL.md"), f"{skill}\n")
        write(os.path.join(self.codes, "ego-beta", "skills", "sk-beta", "SKILL.md"), f"{BETA}\n")
        codex = os.path.join(self.tmp, "codex")
        write(os.path.join(codex, "skills", "codex-own", "SKILL.md"), "own\n")
        write(os.path.join(codex, "skills", "sk-keep", "SKILL.md"), "not ours\n")
        code, text = self.run_render("--company", "alpha", "--codex-home", codex)
        self.assertEqual(code, 0, text)
        self.assertEqual(sorted(os.listdir(os.path.join(codex, "skills"))),
                         [".company-skills.json", "codex-own", "sk-alpha", "sk-keep"])  # sk-claude is claude_only
        # a skill that left the layer is removed; a folder we never recorded is not
        shutil.rmtree(os.path.join(self.codes, "ego-alpha", "skills", "sk-alpha"))
        self.assertEqual(self.run_render("--company", "alpha", "--codex-home", codex)[0], 0)
        self.assertEqual(sorted(os.listdir(os.path.join(codex, "skills"))), [".company-skills.json", "codex-own", "sk-keep"])

    def test_a_codex_folder_with_the_same_name_that_is_not_ours_is_left_alone(self) -> None:
        write(os.path.join(self.codes, "ego-alpha", "skills", "sk-alpha", "SKILL.md"), "ours\n")
        codex = os.path.join(self.tmp, "codex")
        write(os.path.join(codex, "skills", "sk-alpha", "SKILL.md"), "theirs\n")
        self.assertEqual(self.run_render("--company", "alpha", "--codex-home", codex)[0], 0)
        with open(os.path.join(codex, "skills", "sk-alpha", "SKILL.md"), encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "theirs\n")

    def test_over_the_limit_is_not_written(self) -> None:
        codex = os.path.join(self.tmp, "codex")
        os.makedirs(codex)
        code, text = self.run_render("--company", "alpha", "--codex-home", codex, "--max-bytes", "50")
        self.assertEqual(code, 1)
        self.assertIn("not written", text)
        self.assertFalse(os.path.exists(os.path.join(codex, "AGENTS.md")))


class RegressionWithoutCompanyTest(CompanySandbox):
    """Without --company the output is the same as before the flag existed."""

    def test_default_root_claude_md_is_byte_identical_to_the_pre_flag_format(self) -> None:
        home = os.path.join(self.tmp, "claude-home")
        for f in ("rules-general.md", "glossary-alpha.md", "me.md"):
            write(os.path.join(home, f), "x\n")
        man = layers.load_manifest(self.manifest)
        expected = (compose.HEADER + "\n## General rules (superego)\n@~/.claude/rules-general.md\n\n"
                    "## Company (ego)\n@~/.claude/glossary-alpha.md\n\n## User (id)\n@~/.claude/me.md\n\n"
                    + compose.FOOTER)
        self.assertEqual(compose.root_claude_md(man, home), expected)

    def test_default_cli_still_writes_claude_md_and_renders_agents_md_from_the_claude_home(self) -> None:
        home, codex = os.path.join(self.tmp, "claude-home"), os.path.join(self.tmp, "codex")
        os.makedirs(codex)
        write(os.path.join(home, "me.md"), "personal body\n")
        write(os.path.join(home, "harness", "codex.md"), "CODEX ADAPTER\n")
        r = subprocess.run([sys.executable, "-I", os.path.join(ROOT, "tools", "compose.py"), "--manifest", self.manifest,
                            "--claude-home", home, "--codex-home", codex], capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        with open(os.path.join(home, "CLAUDE.md"), encoding="utf-8") as fh:
            self.assertIn("@~/.claude/me.md", fh.read())
        with open(os.path.join(codex, "AGENTS.md"), encoding="utf-8") as fh:
            self.assertIn("personal body", fh.read())

    def test_tilde_imports_still_resolve_against_the_claude_home(self) -> None:
        home = os.path.join(self.tmp, "h")
        write(os.path.join(home, "CLAUDE.md"), "@~/.claude/a.md\n")
        write(os.path.join(home, "a.md"), "A BODY\n")
        self.assertIn("A BODY", render_harness.render_agents_md(home))


if __name__ == "__main__":
    unittest.main()
