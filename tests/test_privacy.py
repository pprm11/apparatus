"""Generic privacy runtime data and optional per-person overrides, entirely offline."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
import privacy  # noqa: E402


class PrivacyConfigTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = Path(tmp.name)
        self.generic = self.home / "generic.json"
        self.local = self.home / "context" / "privacy-terms.local.json"
        self.local.parent.mkdir()
        self.cfg = {"patterns": [{"name": "generic", "regex": "generic-value"}],
                    "forbidden_layer_repos": ["blocked-shared"], "personal_levels": ["id"]}
        self.generic.write_text(json.dumps(self.cfg), encoding="utf-8")
        patcher = mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": str(self.local.parent)})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_missing_local_file_uses_generic_config(self):
        self.assertEqual(privacy.load_config(self.generic), self.cfg)

    def test_generic_duplicates_are_removed_even_without_a_local_file(self):
        self.cfg["patterns"] *= 2
        self.cfg["personal_levels"] *= 2
        self.generic.write_text(json.dumps(self.cfg), encoding="utf-8")
        cfg = privacy.load_config(self.generic)
        self.assertEqual(len(cfg["patterns"]), 1)
        self.assertEqual(cfg["personal_levels"], ["id"])

    def test_local_config_unions_all_lists_without_duplicates(self):
        local = {"patterns": [self.cfg["patterns"][0], {"name": "person", "regex": "restricted-person"}],
                 "forbidden_layer_repos": ["blocked-shared", "private-repo"], "personal_levels": ["id", "ego"]}
        self.local.write_text(json.dumps(local), encoding="utf-8")
        cfg = privacy.load_config(self.generic)
        self.assertEqual(cfg["patterns"], local["patterns"])
        self.assertEqual(cfg["forbidden_layer_repos"], local["forbidden_layer_repos"])
        self.assertEqual(cfg["personal_levels"], local["personal_levels"])
        hits = privacy.scan_text("generic-value restricted-person", privacy.patterns(cfg), "fixture")
        self.assertEqual([h.rule for h in hits], ["generic", "person"])
        self.assertEqual(privacy.forbidden_layer("private-repo", cfg), "private-repo")
        self.assertEqual([h.rule for h in privacy.scan_text(
            "generic-value restricted-person", privacy.patterns(cfg, allow_words=["restricted-person"]), "fixture")],
            ["generic"])

    def test_same_name_different_regex_keeps_both_protections(self):
        self.local.write_text(json.dumps({"patterns": [{"name": "generic", "regex": "extra-value"}]}), encoding="utf-8")
        cfg = privacy.load_config(self.generic)
        self.assertEqual(len(cfg["patterns"]), 2)
        self.assertEqual(len(privacy.scan_text("generic-value extra-value", privacy.patterns(cfg), "fixture")), 2)

    def test_default_local_file_is_in_the_person_context_home(self):
        local = {"patterns": [{"name": "person", "regex": "restricted-person"}]}
        expected = self.home / ".claude" / "privacy-terms.local.json"
        expected.parent.mkdir()
        expected.write_text(json.dumps(local), encoding="utf-8")
        with mock.patch.dict(os.environ, {"CLAUDE_CONFIG_DIR": ""}), mock.patch("pathlib.Path.home", return_value=self.home):
            self.assertEqual(len(privacy.load_config(self.generic)["patterns"]), 2)

    def test_invalid_local_file_fails_closed(self):
        self.local.write_text("{broken", encoding="utf-8")
        with self.assertRaises(ValueError):
            privacy.load_config(self.generic)

    def test_explicit_context_home_overrides_the_process_default(self):
        other = self.home / "other-context"
        other.mkdir()
        (other / "privacy-terms.local.json").write_text(json.dumps({
            "patterns": [{"name": "explicit-context", "regex": "private-person"}]}), encoding="utf-8")
        cfg = privacy.load_config(self.generic, context_home=other)
        self.assertEqual([p["name"] for p in cfg["patterns"]], ["generic", "explicit-context"])


class GenericTermsTest(unittest.TestCase):
    def test_repo_terms_cover_generic_identifier_classes(self):
        cfg = json.loads((ROOT / "ci" / "privacy-terms.json").read_text(encoding="utf-8"))
        cases = {"email": "person@" + "private.invalid", "cpf": "123.456.789-01", "cnpj": "12.345.678/0001-90",
                 "phone": "+55 (11) 91234-5678", "ip": "192.168.1.42", "long-id": "0123456789abcdef01234567",
                 "secret-assignment": "password=real-private-value"}
        pats = privacy.patterns(cfg)
        for name, text in cases.items():
            with self.subTest(name=name):
                self.assertIn(name, [h.rule for h in privacy.scan_text(text, pats, "fixture")])
        self.assertEqual({p["name"] for p in cfg["patterns"]}, set(cases))
        self.assertEqual(cfg["forbidden_layer_repos"], [])
        self.assertEqual(cfg["personal_levels"], ["id"])


if __name__ == "__main__":
    unittest.main()
