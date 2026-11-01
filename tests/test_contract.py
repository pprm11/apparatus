"""Contract tests: a breaking change to superego's public contract fails here (GOVERNANCE.md, docs/contract.md).

ci/contract.json is the snapshot of what other layers, the installer and psique rely on. The live tree may
grow beyond it (additive, minor release) but every snapshot entry must still exist. Removing or renaming one
is a breaking change: it needs a major release, so update the snapshot only together with that release.
"""
import importlib.util
import json
import re
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location("contract_snapshot", ROOT / "ci" / "contract_snapshot.py")
snapshot = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(snapshot)

HOW = "Breaking change to the public contract (GOVERNANCE.md): keep it, deprecate it for one minor release, or ship a major."
SNAP = json.loads((ROOT / "ci" / "contract.json").read_text(encoding="utf-8"))
LIVE = snapshot.live()


def missing(section: str) -> list[str]:
    return snapshot.contains(SNAP[section], LIVE.get(section), section)


class ContractTest(unittest.TestCase):
    def test_snapshot_has_every_section(self) -> None:
        for key in ("layer_json_keys", "manifest_keys", "manifest_layer_keys", "context_budget_keys", "cli",
                    "template_files", "read_paths", "rule_ids", "skills"):
            self.assertIn(key, SNAP)
            self.assertTrue(SNAP[key], f"{key} is empty in ci/contract.json")

    def test_layer_json_keys_kept(self) -> None:
        self.assertEqual(missing("layer_json_keys"), [], HOW)

    def test_manifest_template_keys_kept(self) -> None:
        self.assertEqual(missing("manifest_keys"), [], HOW)

    def test_manifest_layer_keys_still_read(self) -> None:
        """layers.py and compose.py must keep reading every key a manifest layer entry can carry."""
        src = (ROOT / "tools" / "layers.py").read_text(encoding="utf-8") + (ROOT / "tools" / "compose.py").read_text(encoding="utf-8")
        gone = [k for k in SNAP["manifest_layer_keys"] if not re.search(rf"""["']{k}["']""", src)]
        self.assertEqual(gone, [], HOW)

    def test_context_budget_keys_kept(self) -> None:
        src = (ROOT / "tools" / "context_budget.py").read_text(encoding="utf-8")
        gone = [k for k in SNAP["context_budget_keys"] if k not in src]
        self.assertEqual(gone, [], HOW)

    def test_cli_commands_and_flags_kept(self) -> None:
        self.assertEqual(missing("cli"), [], HOW)

    def test_template_files_kept(self) -> None:
        self.assertEqual(missing("template_files"), [], HOW)

    def test_paths_other_layers_read_kept(self) -> None:
        self.assertEqual(missing("read_paths"), [], HOW)

    def test_rule_ids_kept(self) -> None:
        """Files named in layer.json globals/rules and cited by other layers keep their names."""
        self.assertEqual(missing("rule_ids"), [], HOW)

    def test_skills_kept(self) -> None:
        self.assertEqual(missing("skills"), [], HOW)

    def test_removal_is_detected(self) -> None:
        """The detector itself: a snapshot entry the live tree lacks is reported."""
        fake = {"cli": {"onboard": {"commands": {"init": ["--flag-that-does-not-exist"]}}}, "skills": ["no-such-skill"]}
        found = snapshot.contains(fake, LIVE)
        self.assertEqual(len(found), 2, found)
        self.assertEqual(snapshot.contains({"skills": LIVE["skills"][:2]}, LIVE), [])


class ChangelogTest(unittest.TestCase):
    def test_changelog_keeps_a_changelog_shape(self) -> None:
        text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        self.assertIn("## [Unreleased]", text)
        heads = re.findall(r"^## \[(\d+\.\d+\.\d+)\] - \d{4}-\d{2}-\d{2}$", text, re.M)
        self.assertEqual(heads, sorted(heads, key=lambda v: tuple(map(int, v.split("."))), reverse=True))

    def test_breaking_release_bumps_major(self) -> None:
        """A `### Removed` or `### Breaking` section is allowed only in a release whose major bumped."""
        text = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
        blocks = re.split(r"^## ", text, flags=re.M)[1:]
        versions = [(b.split("]")[0].lstrip("["), b) for b in blocks]
        released = [(v, b) for v, b in versions if re.fullmatch(r"\d+\.\d+\.\d+", v)]
        for (v, body), (prev, _) in zip(released, released[1:] + [("0.0.0", "")]):
            if re.search(r"^### (Removed|Breaking)", body, re.M) and v.split(".")[0] != "0":
                self.assertGreater(int(v.split(".")[0]), int(prev.split(".")[0]), f"{v} removes things without a major bump")


class NoIdentifiersTest(unittest.TestCase):
    """superego carries no person or company identifier. Patterns come from ci/privacy-terms.json (the one list the
    installer, CI and tests share); tests/test_generic.py keeps its own list and the CI deny gate adds machine paths."""

    PATTERNS = json.loads((ROOT / "ci" / "privacy-terms.json").read_text(encoding="utf-8"))["patterns"]
    # Files that must name the terms because they define or test the gates, plus third-party skill text.
    DEFINERS = ("ci/", "kits/collective/ci/", "docs/ci-gates.md", "tests/test_generic.py", "tests/test_contract.py",
                "GOVERNANCE.md", "skills/neon/", "skills/neon-postgres/")
    # Known debt found by the sweep (personal-data sweep report, kept outside the repo): the skill is in layer.json install_exclude and
    # must be genericised before superego opens. Ratchet: this set only shrinks; a new file fails the test.
    DEBT = {"skills/engenharia-em-etapas/": {"vendor-gupshup"}}
    # The only handle that may appear: the repository owner's, inside a GitHub URL (install and clone commands).
    OWNER_URL = re.compile(r"github\.com[/:](?:" + next(p["regex"] for p in PATTERNS if p["name"] == "owner-account") + r")/(superego|psique|id-context)")

    def tracked(self) -> list[str]:
        out = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z"], capture_output=True, text=True, encoding="utf-8")
        if out.returncode != 0:
            self.skipTest("not a git checkout")
        return [p for p in out.stdout.split("\0") if p and not p.startswith(self.DEFINERS)]

    def test_no_person_or_company_identifier_in_tracked_text(self) -> None:
        rx = [(p["name"], re.compile(p["regex"], re.I)) for p in self.PATTERNS]
        hits: list[str] = []
        for rel in self.tracked():
            path = ROOT / rel
            names = [(0, rel)]
            try:
                names += list(enumerate(path.read_text(encoding="utf-8").splitlines(), 1))
            except (UnicodeDecodeError, OSError):
                pass
            for n, line in names:
                line = self.OWNER_URL.sub("", line)
                for name, r in rx:
                    if r.search(line) and not any(rel.startswith(d) and name in v for d, v in self.DEBT.items()):
                        hits.append(f"{rel}:{n} [{name}]")
        self.assertEqual(hits, [], "person or company identifier in superego (move it to collective, ego or id):\n" + "\n".join(hits[:40]))

    def test_debt_is_still_debt(self) -> None:
        """A DEBT entry whose hits are gone must be deleted, so the ratchet tightens."""
        for prefix, names in self.DEBT.items():
            rx = [re.compile(p["regex"], re.I) for p in self.PATTERNS if p["name"] in names]
            found = any(r.search(l) for rel in self.tracked() if rel.startswith(prefix)
                        for l in (ROOT / rel).read_text(encoding="utf-8", errors="replace").splitlines() for r in rx)
            self.assertTrue(found, f"{prefix} no longer matches {sorted(names)}: remove it from DEBT")

    def test_privacy_terms_cover_the_known_identifier_classes(self) -> None:
        """The pattern list must not shrink silently: owner, company, product, client and colleague classes stay."""
        names = {p["name"] for p in self.PATTERNS}
        for prefix in ("owner-", "company-", "client-", "colleague-", "product-"):
            self.assertTrue(any(n.startswith(prefix) for n in names), f"no `{prefix}*` pattern left in ci/privacy-terms.json")
        self.assertTrue({"owner-name", "owner-account", "owner-email"} <= names)


if __name__ == "__main__":
    sys.exit(unittest.main())
