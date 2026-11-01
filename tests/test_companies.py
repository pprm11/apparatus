"""tools/companies.py: folder -> company from companies.json (offline, fictional companies)."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import companies  # noqa: E402

DATA = {
    "companies": {
        "alpha": {"prefixes": ["~/Codes/alpha-*", "~/Codes/shared", "~/Codes/alpha"],
                  "home": {"claude": "~/.agent-homes/alpha/claude", "codex": "~/.agent-homes/alpha/codex"}},
        "beta": {"prefixes": ["~/Codes/beta", "~/Codes/beta/*", "~/Codes/**/vendor-beta", "~/Codes/shared-beta"]},
    },
    "default": None,
}
HOME = os.path.expanduser("~")


def of(path: str) -> str | None:
    return companies.company_of(path, DATA)


class CompanyOfTest(unittest.TestCase):
    def test_glob_matches_the_folder_and_everything_below(self) -> None:
        self.assertEqual(of("~/Codes/alpha-app"), "alpha")
        self.assertEqual(of("~/Codes/alpha-app/src/deep/file.py"), "alpha")
        self.assertEqual(of("~/Codes/beta/service/x"), "beta")

    def test_star_stays_inside_one_segment_and_double_star_crosses(self) -> None:
        self.assertIsNone(of("~/Codes/x/alpha-app"))  # alpha-* is anchored at ~/Codes
        self.assertEqual(of("~/Codes/team/deep/vendor-beta/lib"), "beta")

    def test_no_match_is_none(self) -> None:
        self.assertIsNone(of("~/Codes/unmapped"))
        self.assertIsNone(of("~/Codes"))
        self.assertIsNone(of("~/Codes/sharedextra"))  # a prefix is a whole segment unless it has a glob

    def test_first_match_wins_in_file_order(self) -> None:
        both = {"companies": {"one": {"prefixes": ["~/Codes/x*"]}, "two": {"prefixes": ["~/Codes/x*"]}}}
        self.assertEqual(companies.company_of("~/Codes/xy", both), "one")
        self.assertEqual(companies.companies_of("~/Codes/xy", both), ["one", "two"])

    def test_tilde_backslashes_and_absolute_paths_are_equivalent(self) -> None:
        absolute = os.path.join(HOME, "Codes", "alpha-app")
        self.assertEqual(of(absolute), "alpha")
        if sys.platform == "win32":  # a backslash is an ordinary file name character on POSIX
            self.assertEqual(of(absolute.replace("/", "\\")), "alpha")
        self.assertEqual(of(Path(absolute) / "sub"), "alpha")

    def test_trailing_slash_and_pathlike_input(self) -> None:
        self.assertEqual(of("~/Codes/alpha-app/"), "alpha")

    @unittest.skipUnless(companies.CASE_INSENSITIVE, "case is significant on this OS")
    def test_case_is_ignored_on_windows_and_macos(self) -> None:
        self.assertEqual(of("~/CODES/Alpha-App"), "alpha")

    def test_owner_of_also_knows_the_agent_homes(self) -> None:
        home = os.path.join(HOME, ".agent-homes", "alpha", "claude", "projects")
        self.assertIsNone(companies.company_of(home, DATA))
        self.assertEqual(companies.owner_of(home, DATA), "alpha")
        self.assertIsNone(companies.owner_of("~/.agent-homes/other", DATA))


class HomeAndLoadTest(unittest.TestCase):
    def test_home_of_expands_tilde_per_harness(self) -> None:
        self.assertEqual(companies.home_of("alpha", "claude", DATA), Path(HOME) / ".agent-homes" / "alpha" / "claude")
        self.assertEqual(companies.home_of("alpha", "codex", DATA), Path(HOME) / ".agent-homes" / "alpha" / "codex")

    def test_home_of_unknown_or_undeclared_is_none_and_bad_harness_raises(self) -> None:
        self.assertIsNone(companies.home_of("beta", "claude", DATA))
        self.assertIsNone(companies.home_of("nobody", "claude", DATA))
        with self.assertRaises(ValueError):
            companies.home_of("alpha", "vim", DATA)

    def test_load_reads_a_file_and_rejects_a_file_without_companies(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            good, bad = os.path.join(tmp, "c.json"), os.path.join(tmp, "bad.json")
            Path(good).write_text(json.dumps(DATA), encoding="utf-8")
            Path(bad).write_text("{}", encoding="utf-8")
            self.assertEqual(companies.company_of("~/Codes/alpha-x", companies.load(good)), "alpha")
            with self.assertRaises(ValueError):
                companies.load(bad)
            with self.assertRaises(FileNotFoundError):
                companies.load(os.path.join(tmp, "missing.json"))


if __name__ == "__main__":
    unittest.main()
