"""The real layer repos composed per company (skipped where the repos are not checked out, e.g. in CI).

Terms come from lists that already exist: ego-socioia/ci/deny-terms.txt (regex per line) and
collective-socioia/.denylist.companies.local (literal per line). Nothing is hardcoded here.

Status of the neutrality test: the id layer on its main branch still names the other company in three of its
loaded texts, so the Socio IA home fails it TODAY. It is marked expectedFailure until the id-context PR
"company-neutral id texts" is merged. When that happens set ID_PR_MERGED = True (an unexpected success is
reported as a failure on purpose, as the reminder). To see it pass now, point COMPOSE_TEST_ID_DIR at a checkout
of that PR branch.
"""
import os
import re
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import compose  # noqa: E402
import companies  # noqa: E402
import layers  # noqa: E402

ID_PR_MERGED = True

CODES = os.path.expanduser("~/Codes")
MANIFEST = os.path.expanduser(os.environ.get("PSIQUE_MANIFEST", os.path.join(CODES, "psique", "manifest.json")))
COMPANIES = os.path.expanduser(os.environ.get("COMPANIES_FILE", "~/.claude/companies.json"))
DENY_REGEX = os.path.join(CODES, "ego-socioia", "ci", "deny-terms.txt")
DENY_LITERAL = os.path.join(CODES, "collective-socioia", ".denylist.companies.local")
ID_OVERRIDE = os.environ.get("COMPOSE_TEST_ID_DIR")

HAVE_REPOS = all(os.path.exists(p) for p in (MANIFEST, COMPANIES, DENY_REGEX, DENY_LITERAL))


def deny_patterns() -> list[re.Pattern]:
    out = []
    for path, literal in ((DENY_REGEX, False), (DENY_LITERAL, True)):
        with open(path, encoding="utf-8") as fh:
            for line in fh.read().splitlines():
                line = line.strip()
                if line and not line.startswith("#"):
                    out.append(re.compile(rf"(?<!\w){re.escape(line)}(?!\w)" if literal else line, re.I))
    return out


def load_manifest() -> dict:
    man = layers.load_manifest(MANIFEST)
    if ID_OVERRIDE:
        for layer in man["layers"]:
            if layer["level"] == "id":
                layer["path"] = os.path.expanduser(ID_OVERRIDE)
                layer["config"] = layers.read_json(os.path.join(layer["path"], "layer.json"))
    return man


def expected_failure_until_id_pr_is_merged(test):
    return test if (ID_PR_MERGED or ID_OVERRIDE) else unittest.expectedFailure(test)


@unittest.skipUnless(HAVE_REPOS, "needs the real layer repos under ~/Codes")
class RealCompositionTest(unittest.TestCase):
    @expected_failure_until_id_pr_is_merged
    def test_socioia_home_has_no_term_of_the_other_company(self) -> None:
        man = load_manifest()
        man["budgets"] = {}  # budgets have their own test in psique; this one is about terms
        with tempfile.TemporaryDirectory() as out:
            rc = compose.compose_company(man, "socioia", companies.load(COMPANIES), out, CODES, note=lambda m: None)
            self.assertEqual(rc, 0)
            hits = []
            for root, _, names in os.walk(out):
                for name in names:
                    path = os.path.join(root, name)
                    with open(path, encoding="utf-8") as fh:
                        text = fh.read()
                    hits += [f"{os.path.relpath(path, out)}" for rx in deny_patterns() if rx.search(text)]
            self.assertEqual(sorted(set(hits)), [], "files of the Socio IA home that carry a term of the other company")

    def test_the_company_layer_split_keeps_the_other_ego_out(self) -> None:
        man = load_manifest()
        man["budgets"] = {}
        with tempfile.TemporaryDirectory() as out:
            self.assertEqual(compose.compose_company(man, "socioia", companies.load(COMPANIES), out, CODES, note=lambda m: None), 0)
            files = os.listdir(os.path.join(out, "global"))
            others = [name for name in companies.load(COMPANIES)["companies"] if name != "socioia"]
            self.assertIn("glossario-socioia.md", files)
            self.assertFalse([f for f in files for other in others if f.endswith(f"-{other}.md")], files)


if __name__ == "__main__":
    unittest.main()
