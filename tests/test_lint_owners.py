"""Offline registered-reference behavior, using synthetic temporary homes only."""
from __future__ import annotations

import contextlib
import dataclasses
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

if "tools.lint_owners" not in sys.modules:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools import lint_owners as lint


def parameter(name="limit", regex=r"limit = (?P<value>\w+)"):
    return {"name": name, "extractor_regex": regex, "unit": "rounds"}


def reference(path="copy.md", label="expansion", anchor=r"(?m)^limit = [^\n]+$", **changes):
    result = {"path": path, "anchor": anchor, "label": label}
    if label == "expansion":
        result["parameters"] = ["limit"]
    result.update(changes)
    return result


def document(**changes):
    policy = {
        "id": "sample-policy",
        "owner": {"path": "rules/source.md", "anchor": r"(?m)^# Source\nlimit = [^\n]+$"},
        "parameters": [parameter()], "extractor_version": "2", "references": [],
    }
    policy.update(changes)
    return {"policies": [policy]}


class ContextFixture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.root = self.base / "context"
        self.contracts = self.base / "contracts"
        self.root.mkdir()
        self.contracts.mkdir()
        self.write("rules/source.md", "# Source\nlimit = 2\n")
        self.contract()

    def write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def contract(self, policies=None, aliases=None):
        for name, data in (
            ("policies.json", policies if policies is not None else document()),
            ("project-aliases.json", {"aliases": aliases or {}}),
        ):
            (self.contracts / name).write_text(json.dumps(data), encoding="utf-8")

    def scan(self):
        return lint.check(self.root, lint.load_contracts(self.contracts))

    def cli(self, *flags):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            status = lint.main(["--root", str(self.root), "--contracts", str(self.contracts), *flags])
        return status, out.getvalue(), err.getvalue()

    def pointer(self, text):
        self.write("copy.md", text)
        self.contract(document(references=[reference(label="pointer", anchor=r"(?s)\A.+\Z")]))


class ReferenceChecksTest(ContextFixture):
    def test_matching_expansion_is_silent(self):
        self.write("copy.md", "limit = two\n")
        self.contract(document(references=[reference()]))
        self.assertEqual(self.scan(), [])

    def test_unlisted_files_and_other_passages_are_never_scanned(self):
        self.write("unlisted.md", "limit = 9\n[[absent]]\n")
        self.write("rules/source.md", "# Source\nlimit = 2\n\n# Other\nlimit = 9\n")
        self.write("copy.md", "limit = 9\n\n# Selected\nlimit = 2\n")
        self.contract(document(references=[reference(anchor=r"(?m)^# Selected\nlimit = [^\n]+$")]))
        with patch.object(Path, "glob", side_effect=AssertionError("corpus scan")):
            self.assertEqual(self.scan(), [])

    def test_manifest_is_neither_required_nor_read(self):
        (self.contracts / "corpus-manifest.json").write_text("invalid JSON", encoding="utf-8")
        self.assertEqual(self.scan(), [])

    def test_owner_missing_file_and_anchor_have_their_own_kind(self):
        for text in (None, "# Renamed\nlimit = 2\n"):
            with self.subTest(text=text):
                if text is None:
                    (self.root / "rules/source.md").unlink()
                else:
                    self.write("rules/source.md", text)
                finding, = self.scan()
                self.assertIsInstance(finding, lint.OwnerMissing)
                self.assertEqual(finding.kind, "owner_missing")
                self.assertEqual(self.cli("--strict")[0], 1)

    def test_owner_parser_drift_is_blocking(self):
        self.contract(document(parameters=[parameter(regex=r"cap = (?P<value>\d+)")]))
        finding, = self.scan()
        self.assertIsInstance(finding, lint.OwnerParserDrift)
        self.assertEqual(finding.kind, "owner_parser_drift")
        self.assertEqual(self.cli("--strict")[0], 1)

    def test_empty_owner_capture_is_parser_drift(self):
        self.contract(document(parameters=[parameter(regex=r"limit = (?P<value>)")]))
        self.assertEqual([f.kind for f in self.scan()], ["owner_parser_drift"])

    def test_conflicting_owner_values_are_parser_drift(self):
        self.write("rules/source.md", "# Source\nlimit = 2\nlimit = 3\n")
        self.contract(document(owner={"path": "rules/source.md", "anchor": r"(?s)\A.+\Z"}))
        self.assertEqual([f.kind for f in self.scan()], ["owner_parser_drift"])

    def test_reference_missing_file_and_anchor_are_advisory(self):
        self.contract(document(references=[reference()]))
        for text in (None, "# Renamed\n"):
            with self.subTest(text=text):
                if text is not None:
                    self.write("copy.md", text)
                finding, = self.scan()
                self.assertIsInstance(finding, lint.ReferenceMissing)
                self.assertEqual(finding.kind, "reference_missing")
                self.assertEqual(self.cli("--strict")[0], 0)

    def test_ambiguous_anchor_never_chooses_a_passage(self):
        self.write("copy.md", "limit = 2\nlimit = 2\n")
        self.contract(document(references=[reference()]))
        self.assertEqual([f.kind for f in self.scan()], ["reference_missing"])

    def test_pointer_missing_owner_link_is_advisory(self):
        self.pointer("Follow the global policy.\n[[unrelated]]\n")
        finding, = self.scan()
        self.assertIsInstance(finding, lint.PointerMissingLink)
        self.assertEqual(finding.kind, "pointer_missing_link")
        self.assertEqual(self.cli("--strict")[0], 0)

    def test_pointer_link_forms_name_the_owner(self):
        for text in ("[[rules/source]]", "[[rules/source.md|read]]", "`rules/source.md`", "See Source."):
            with self.subTest(text=text):
                self.pointer(text)
                self.assertEqual(self.scan(), [])

    def test_skill_name_can_link_to_skill_owner(self):
        self.write("skills/sample/SKILL.md", "# Source\nlimit = 2\n")
        self.write("copy.md", "Use the `sample` skill.\n")
        self.contract(document(owner={"path": "skills/sample/SKILL.md", "anchor": r"(?s)\A.+\Z"},
                               references=[reference(label="pointer", anchor=r"(?s)\A.+\Z")]))
        self.assertEqual(self.scan(), [])

    def test_pointer_states_even_a_matching_value_is_blocking(self):
        self.pointer("See `rules/source.md`. limit = 2\n")
        finding, = self.scan()
        self.assertIsInstance(finding, lint.PointerStatesValue)
        self.assertEqual((finding.kind, finding.value, finding.owner_value),
                         ("pointer_states_value", "2", "2"))
        self.assertEqual(self.cli()[0], 0)
        self.assertEqual(self.cli("--strict")[0], 1)

    def test_expansion_mismatch_uses_current_line(self):
        self.write("copy.md", "Introduction\n\nlimit = 3\n")
        self.contract(document(references=[reference()]))
        finding, = self.scan()
        self.assertIsInstance(finding, lint.ExpansionValueMismatch)
        self.assertEqual((finding.kind, finding.path, finding.line, finding.value, finding.owner_value),
                         ("expansion_value_mismatch", "copy.md", 3, "3", "2"))
        self.assertEqual(self.cli("--strict")[0], 1)

    def test_missing_expansion_capture_fails_closed(self):
        self.write("copy.md", "The format has changed.\n")
        self.contract(document(references=[reference(anchor=r"(?s)\A.+\Z")]))
        finding, = self.scan()
        self.assertEqual((finding.kind, finding.value), ("expansion_value_mismatch", None))

    def test_expansion_checks_all_occurrences(self):
        self.write("copy.md", "limit = 2\nlimit = 9\n")
        self.contract(document(references=[reference(anchor=r"(?s)\A.+\Z")]))
        finding, = self.scan()
        self.assertEqual((finding.kind, finding.value, finding.line), ("expansion_value_mismatch", "9", 2))

    def test_expansion_checks_only_declared_parameters(self):
        self.write("rules/source.md", "# Source\nlimit = 2\ncap = 4\n")
        self.write("copy.md", "limit = 2\ncap = 9\n")
        self.contract(document(owner={"path": "rules/source.md", "anchor": r"(?s)\A.+\Z"},
                               parameters=[parameter(), parameter("cap", r"cap = (?P<value>\d+)")],
                               references=[reference(anchor=r"(?s)\A.+\Z")]))
        self.assertEqual(self.scan(), [])

    def test_historical_passage_only_checks_presence(self):
        self.write("copy.md", "limit = 9\n[[absent]]\n")
        self.contract(document(references=[reference(label="historical")]))
        self.assertEqual(self.scan(), [])
        (self.root / "copy.md").unlink()
        self.assertEqual([f.kind for f in self.scan()], ["reference_missing"])

    def test_distinct_scoped_instruction_repeats_no_owner_parameter(self):
        self.write("copy.md", "A separate repair loop has limit = 9.\n")
        self.contract(document(references=[reference(anchor=r"(?s)\A.+\Z", parameters=[])]))
        self.assertEqual(self.scan(), [])

    def test_stale_alias_only_checks_registered_memory_key(self):
        self.contract(aliases={"old-key": "current-key"})
        self.write("projects/old-key/session.jsonl", "{}\n")
        self.write("projects/unlisted-key/memory/item.md", "data\n")
        self.assertEqual(self.scan(), [])
        self.write("projects/old-key/memory/nested/item.md", "data\n")
        finding, = self.scan()
        self.assertIsInstance(finding, lint.StaleAlias)
        self.assertEqual((finding.kind, finding.value, finding.owner_value),
                         ("stale_alias", "old-key", "current-key"))
        self.assertEqual(self.cli("--strict")[0], 0)

    def test_unreadable_registered_source_has_a_typed_finding(self):
        (self.root / "rules/source.md").write_bytes(b"\xff")
        self.assertEqual([f.kind for f in self.scan()], ["owner_missing"])

    def test_normalization_table(self):
        for raw, normalized in (("  HIGH\n role ", "high role"), ("M\u00c9DIO", "medio"),
                                ("two", "2"), ("dois", "2"), ("duas", "2"),
                                ("２", "2"), ("2", "2"), ("0.8", "0.8"),
                                ("Two rodadas", "2 rodadas")):
            with self.subTest(raw=raw):
                self.assertEqual(lint.normalize_value(raw), normalized)

    def test_planted_drift_set_has_full_recall_and_precision(self):
        references, planted = [], set()
        for index in range(10):
            name = f"copies/ref-{index}.md"
            self.write(name, "limit = dois\n")
            references.append(reference(path=name))
            if index < 5:
                planted.add(name)
        self.contract(document(references=references))
        self.assertEqual(self.scan(), [])
        for name in planted:
            self.write(name, "limit = 9\n")
        findings = self.scan()
        self.assertEqual(len(findings), 5)
        self.assertEqual({f.path for f in findings}, planted)
        self.assertEqual({f.kind for f in findings}, {"expansion_value_mismatch"})

    def test_reference_can_choose_a_registered_scoped_owner(self):
        self.write("rules/scoped.md", "# Scoped\nlimit = 7\n")
        self.write("copy.md", "limit = 7\n")
        scoped = {"owner": {"path": "rules/scoped.md", "anchor": r"(?s)\A.+\Z"},
                  "parameters": [parameter()]}
        self.contract(document(scoped_owners=[scoped],
                               references=[reference(owner="rules/scoped.md")]))
        self.assertEqual(self.scan(), [])
        self.write("copy.md", "limit = 8\n")
        finding, = self.scan()
        self.assertEqual((finding.kind, finding.owner_value), ("expansion_value_mismatch", "7"))


class ContractAndCliTest(ContextFixture):
    def test_unconfigured_contracts_are_one_advisory_without_reading_context(self):
        for flags in ([], ["--strict"], ["--json"], ["--json", "--strict"]):
            with self.subTest(flags=flags):
                out, err = io.StringIO(), io.StringIO()
                with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                    with patch.object(lint, "load_contracts", side_effect=AssertionError("contracts read")):
                        with patch.object(lint, "check", side_effect=AssertionError("context read")):
                            status = lint.main(["--root", str(self.root / "absent"), *flags])
                self.assertEqual((status, out.getvalue(), err.getvalue()),
                                 (0, "no contracts configured\n", ""))

    def test_cli_json_and_markdown_keep_report_shape(self):
        self.write("copy.md", "limit = 9\n")
        self.contract(document(references=[reference()]))
        status, output, error = self.cli("--json", "--strict")
        self.assertEqual((status, error), (1, ""))
        report = json.loads(output)
        self.assertEqual(set(report), {"version", "findings", "counts"})
        self.assertEqual(report["version"], 1)
        self.assertEqual(report["counts"]["expansion_value_mismatch"], 1)
        self.assertEqual(set(report["findings"][0]),
                         {"kind", "policy", "path", "line", "value", "owner_value", "detail"})
        self.assertIn("| Policy | Kind | Path | Line | Value | Owner value | Detail |", self.cli()[1])
        finding, = self.scan()
        with self.assertRaises(dataclasses.FrozenInstanceError):
            finding.path = "changed"

    def test_cli_shadow_never_blocks_on_findings(self):
        (self.root / "rules/source.md").unlink()
        self.assertEqual(self.cli("--json")[0], 0)
        self.assertEqual(self.cli("--json", "--strict")[0], 1)

    def test_unknown_label_parameter_and_version_are_contract_errors(self):
        cases = (
            document(references=[reference(label="extra_declaration")]),
            document(references=[reference(parameters=["unknown"])]),
            document(extractor_version="unknown"), document(parameters=[]),
            document(parameters=[parameter(regex=r"limit = (\d+)")]),
            document(owner={"path": "rules/source.md", "anchor": "["}),
        )
        for data in cases:
            with self.subTest(data=data):
                self.contract(data)
                self.assertEqual(self.cli()[0], 2)

    def test_expansion_parameter_names_are_required(self):
        ref = reference()
        del ref["parameters"]
        self.contract(document(references=[ref]))
        self.assertEqual(self.cli()[0], 2)

    def test_duplicate_keys_policy_ids_and_parameter_names_are_rejected(self):
        self.contract(document(parameters=[parameter(), parameter()]))
        self.assertEqual(self.cli()[0], 2)
        policy = document()["policies"][0]
        self.contract({"policies": [policy, policy]})
        self.assertEqual(self.cli()[0], 2)
        (self.contracts / "policies.json").write_text('{"policies": [], "policies": []}', encoding="utf-8")
        self.assertEqual(self.cli()[0], 2)

    def test_outside_paths_and_alias_chains_are_rejected(self):
        for name in ("../outside.md", "/outside.md", "X:/outside.md", "rules\\source.md"):
            with self.subTest(name=name):
                self.contract(document(references=[reference(path=name)]))
                self.assertEqual(self.cli()[0], 2)
        for aliases in ({"a": "a"}, {"a/b": "c"}, {"a": "b", "b": "c"}):
            with self.subTest(aliases=aliases):
                self.contract(aliases=aliases)
                self.assertEqual(self.cli()[0], 2)


if __name__ == "__main__":
    unittest.main()
