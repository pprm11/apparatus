#!/usr/bin/env python3
"""Verify registered passages against their owners, offline and shadow by default.

python -I tools/lint_owners.py --root CONTEXT_HOME [--contracts CONTRACTS] [--json] [--strict]
Without --contracts, print one advisory line and exit successfully without reading files.
Anchors select passages by regex. Extractors read values from those passages only.
Unlisted files are never discovered. Project aliases check registered memory keys only.
"""
from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import asdict, dataclass, field
import json
from pathlib import Path, PurePosixPath
import re
import sys
import unicodedata


@dataclass(frozen=True, slots=True, kw_only=True)
class Finding:
    policy: str
    path: str
    line: int
    value: str | None
    owner_value: str | None
    detail: str
    kind: str = field(init=False, default="")


@dataclass(frozen=True, slots=True, kw_only=True)
class OwnerMissing(Finding):
    kind: str = field(init=False, default="owner_missing")


@dataclass(frozen=True, slots=True, kw_only=True)
class OwnerParserDrift(Finding):
    kind: str = field(init=False, default="owner_parser_drift")


@dataclass(frozen=True, slots=True, kw_only=True)
class ReferenceMissing(Finding):
    kind: str = field(init=False, default="reference_missing")


@dataclass(frozen=True, slots=True, kw_only=True)
class PointerMissingLink(Finding):
    kind: str = field(init=False, default="pointer_missing_link")


@dataclass(frozen=True, slots=True, kw_only=True)
class PointerStatesValue(Finding):
    kind: str = field(init=False, default="pointer_states_value")


@dataclass(frozen=True, slots=True, kw_only=True)
class ExpansionValueMismatch(Finding):
    kind: str = field(init=False, default="expansion_value_mismatch")


@dataclass(frozen=True, slots=True, kw_only=True)
class StaleAlias(Finding):
    kind: str = field(init=False, default="stale_alias")


FINDING_TYPES = (OwnerMissing, OwnerParserDrift, ReferenceMissing, PointerMissingLink,
                 PointerStatesValue, ExpansionValueMismatch, StaleAlias)
BLOCKING_KINDS = frozenset({"owner_missing", "owner_parser_drift", "pointer_states_value",
                            "expansion_value_mismatch"})
EXTERNAL_OWNER = "../Codes/self/manifest.json"
EXTERNAL_OWNERS = (EXTERNAL_OWNER, "../Codes/psique/manifest.json")


@dataclass(frozen=True, slots=True)
class Selector:
    path: str
    anchor: re.Pattern[str]


@dataclass(frozen=True, slots=True)
class Parameter:
    name: str
    regex: re.Pattern[str]


@dataclass(frozen=True, slots=True)
class Declaration:
    owner: Selector
    parameters: tuple[Parameter, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class Reference:
    selector: Selector
    label: str
    parameters: tuple[str, ...]
    owner: str


@dataclass(frozen=True, slots=True)
class Policy:
    id: str
    declarations: tuple[Declaration, ...]
    references: tuple[Reference, ...]


@dataclass(frozen=True, slots=True)
class Contracts:
    policies: tuple[Policy, ...]
    aliases: tuple[tuple[str, str], ...]


@dataclass(frozen=True, slots=True)
class Passage:
    path: str
    text: str
    line: int


@dataclass(frozen=True, slots=True)
class Capture:
    value: str
    line: int


def normalize_value(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value).casefold()
    plain = "".join(char for char in decomposed if not unicodedata.combining(char))
    digits = "".join(str(unicodedata.decimal(char)) if char.isdecimal() else char for char in plain)
    words = re.sub(r"\b(?:two|dois|duas)\b", "2", digits)
    return " ".join(words.split())


def object_value(value: object) -> dict[str, object]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise ValueError("expected a JSON object")
    return value


def string_value(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("expected a nonempty string")
    return value


def list_value(value: object) -> list[object]:
    if not isinstance(value, list):
        raise ValueError("expected a JSON array")
    return value


def unique_names(names: Sequence[str]) -> None:
    if len(set(names)) != len(names):
        raise ValueError("duplicate identity")


def context_name(value: object, *, owner: bool = False) -> str:
    name = string_value(value)
    if owner and name in EXTERNAL_OWNERS:
        return name
    parts = PurePosixPath(name).parts
    if re.search(r"[\\:]", name) or name.startswith("/") or ".." in parts or not parts:
        raise ValueError(f"source outside --root: {name}")
    return name


def parse_selector(value: object, *, owner: bool = False) -> Selector:
    item = object_value(value)
    anchor = re.compile(string_value(item["anchor"]), re.MULTILINE)
    return Selector(context_name(item["path"], owner=owner), anchor)


def parse_parameter(value: object) -> Parameter:
    item = object_value(value)
    regex = re.compile(string_value(item["extractor_regex"]), re.IGNORECASE)
    if "value" not in regex.groupindex:
        raise ValueError("extractor needs a named value group")
    return Parameter(string_value(item["name"]), regex)


def parse_declaration(value: object) -> Declaration:
    item = object_value(value)
    parameters = tuple(map(parse_parameter, list_value(item["parameters"])))
    if not parameters:
        raise ValueError("owner needs parameters")
    unique_names([parameter.name for parameter in parameters])
    return Declaration(parse_selector(item["owner"], owner=True), parameters)


def parse_reference(value: object, declarations: Sequence[Declaration]) -> Reference:
    item = object_value(value)
    label = string_value(item["label"])
    if label not in ("pointer", "expansion", "historical"):
        raise ValueError("unknown reference label")
    owner = context_name(item.get("owner", declarations[0].owner.path), owner=True)
    declaration = next((entry for entry in declarations if entry.owner.path == owner), None)
    if declaration is None:
        raise ValueError("reference must name a registered owner")
    names = parse_repeated_parameters(item, label, declaration)
    return Reference(selector=parse_selector(item), label=label, parameters=names, owner=owner)


def parse_repeated_parameters(item: dict[str, object], label: str,
                              declaration: Declaration) -> tuple[str, ...]:
    names = tuple(map(string_value, list_value(item.get("parameters", []))))
    unique_names(names)
    known = {parameter.name for parameter in declaration.parameters}
    if label == "expansion" and ("parameters" not in item or not set(names) <= known):
        raise ValueError("expansion needs known parameter names")
    if label != "expansion" and "parameters" in item:
        raise ValueError("only expansions declare repeated parameters")
    return names


def parse_policy(value: object) -> Policy:
    item = object_value(value)
    if item["extractor_version"] != "2":
        raise ValueError("unsupported extractor_version")
    declarations = (parse_declaration(item),
                    *map(parse_declaration, list_value(item.get("scoped_owners", []))))
    unique_names([declaration.owner.path for declaration in declarations])
    references = tuple(parse_reference(ref, declarations) for ref in list_value(item["references"]))
    return Policy(string_value(item["id"]), declarations, references)


def unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"duplicate JSON key: {key}")
        result[key] = value
    return result


def load_document(path: Path) -> dict[str, object]:
    return object_value(json.loads(path.read_text(encoding="utf-8-sig"), object_pairs_hook=unique_object))


def alias_pair(pair: tuple[str, object]) -> tuple[str, str]:
    stale, target = pair
    canonical = context_name(target)
    if "/" in context_name(stale) or "/" in canonical or stale == canonical:
        raise ValueError("alias needs distinct project keys")
    return stale, canonical


def load_contracts(directory: Path) -> Contracts:
    policies = tuple(map(parse_policy, list_value(load_document(directory / "policies.json")["policies"])))
    unique_names([policy.id for policy in policies])
    aliases = object_value(load_document(directory / "project-aliases.json")["aliases"])
    pairs = tuple(map(alias_pair, aliases.items()))
    if any(target in aliases for _, target in pairs):
        raise ValueError("alias chains are unsupported")
    return Contracts(policies, pairs)


def source_path(root: Path, name: str) -> Path:
    if name in EXTERNAL_OWNERS:
        name = next((candidate for candidate in EXTERNAL_OWNERS if (root / candidate).is_file()), name)
    target = (root / name).resolve()
    if name not in EXTERNAL_OWNERS and not target.is_relative_to(root.resolve()):
        raise ValueError(f"source outside --root: {name}")
    return target


def load_passage(root: Path, selector: Selector) -> Passage:
    text = source_path(root, selector.path).read_text(encoding="utf-8-sig")
    matches = list(selector.anchor.finditer(text))
    if len(matches) != 1 or not matches[0].group().strip():
        raise ValueError("anchor must select exactly one nonempty passage")
    match = matches[0]
    return Passage(selector.path, match.group(), text.count("\n", 0, match.start()) + 1)


def captures(parameter: Parameter, passage: Passage) -> list[Capture]:
    result = []
    for match in parameter.regex.finditer(passage.text):
        value = match.group("value")
        if value and value.strip():
            result.append(Capture(normalize_value(value),
                                  passage.line + passage.text.count("\n", 0, match.start("value"))))
    return result


def make_finding(kind: type[Finding], policy: str, path: str, detail: str,
                 line: int = 1, value: str | None = None, owner_value: str | None = None) -> Finding:
    return kind(policy=policy, path=path, line=line, value=value, owner_value=owner_value, detail=detail)


def owner_values(policy: str, declaration: Declaration, passage: Passage) -> tuple[dict[str, str], list[Finding]]:
    values: dict[str, str] = {}
    findings: list[Finding] = []
    for parameter in declaration.parameters:
        hits = captures(parameter, passage)
        distinct = {hit.value for hit in hits}
        if len(distinct) == 1:
            values[parameter.name] = hits[0].value
        else:
            findings.append(make_finding(OwnerParserDrift, policy, passage.path,
                                         f"parameter does not extract one value: {parameter.name}", passage.line))
    return values, findings


def owner_heading(passage: Passage) -> str:
    heading = re.search(r"(?m)^#{1,6}\s+(.+)$", passage.text)
    return heading.group(1).strip() if heading else ""


def owner_names(path: str) -> set[str]:
    pure = PurePosixPath(path)
    names = {path, pure.with_suffix("").as_posix()}
    if pure.name == "SKILL.md":
        names.update((pure.parent.name, pure.parent.as_posix(), pure.parent.name + "/SKILL"))
    elif len(pure.parts) == 1:
        names.update(("global/" + path, "global/" + pure.stem))
    return names


def pointer_names_owner(passage: Passage, owner: Passage) -> bool:
    names = owner_names(owner.path)
    links = re.findall(r"\[\[([^\]\n]+)\]\]|(?<!`)`([^`\n]+)`(?!`)", passage.text)
    targets = ((wiki or code).split("|", 1)[0].split("#", 1)[0] for wiki, code in links)
    if any(target in names for target in targets):
        return True
    heading = owner_heading(owner)
    return bool(heading and re.search(r"(?<!\w)" + re.escape(heading) + r"(?!\w)", passage.text, re.I))


def pointer_findings(policy: str, declaration: Declaration, passage: Passage,
                     owner: Passage, values: dict[str, str]) -> list[Finding]:
    findings = []
    if not pointer_names_owner(passage, owner):
        findings.append(make_finding(PointerMissingLink, policy, passage.path,
                                     "pointer passage does not name its owner", passage.line))
    for parameter in declaration.parameters:
        for hit in captures(parameter, passage):
            findings.append(make_finding(PointerStatesValue, policy, passage.path,
                                         f"pointer repeats parameter: {parameter.name}", hit.line,
                                         hit.value, values.get(parameter.name)))
    return findings


def expansion_findings(policy: str, reference: Reference, declaration: Declaration,
                       passage: Passage, values: dict[str, str]) -> list[Finding]:
    findings = []
    parameters = {parameter.name: parameter for parameter in declaration.parameters}
    for name in reference.parameters:
        if name in values:
            findings.extend(parameter_mismatches(policy, parameters[name], passage, values[name]))
    return findings


def parameter_mismatches(policy: str, parameter: Parameter, passage: Passage, expected: str) -> list[Finding]:
    hits = captures(parameter, passage)
    if not hits:
        return [make_finding(ExpansionValueMismatch, policy, passage.path,
                             f"expansion no longer extracts parameter: {parameter.name}", passage.line,
                             owner_value=expected)]
    return [make_finding(ExpansionValueMismatch, policy, passage.path,
                         f"parameter differs: {parameter.name}", hit.line, hit.value, expected)
            for hit in hits if hit.value != expected]


def reference_findings(root: Path, policy: str, reference: Reference, declaration: Declaration,
                       owner: Passage | None, values: dict[str, str]) -> list[Finding]:
    try:
        passage = load_passage(root, reference.selector)
    except (OSError, UnicodeError, ValueError) as error:
        return [make_finding(ReferenceMissing, policy, reference.selector.path, str(error))]
    if reference.label == "historical" or owner is None:
        return []
    if reference.label == "pointer":
        return pointer_findings(policy, declaration, passage, owner, values)
    return expansion_findings(policy, reference, declaration, passage, values)


def declaration_findings(root: Path, policy: Policy, declaration: Declaration) -> list[Finding]:
    owner: Passage | None = None
    values: dict[str, str] = {}
    findings: list[Finding] = []
    try:
        owner = load_passage(root, declaration.owner)
    except (OSError, UnicodeError, ValueError) as error:
        findings.append(make_finding(OwnerMissing, policy.id, declaration.owner.path, str(error)))
    if owner is not None:
        values, parsed = owner_values(policy.id, declaration, owner)
        findings.extend(parsed)
    for reference in policy.references:
        if reference.owner == declaration.owner.path:
            findings.extend(reference_findings(root, policy.id, reference, declaration, owner, values))
    return findings


def stale_aliases(root: Path, aliases: Sequence[tuple[str, str]]) -> list[Finding]:
    findings = []
    for stale, canonical in aliases:
        memory = source_path(root, f"projects/{stale}/memory")
        for path in sorted(memory.rglob("*")):
            if path.is_file() and path.resolve().is_relative_to(root):
                findings.append(make_finding(StaleAlias, "project-aliases", path.relative_to(root).as_posix(),
                                             "stale project key still contains a memory file",
                                             value=stale, owner_value=canonical))
    return findings


def sorted_findings(findings: Iterable[Finding]) -> list[Finding]:
    return sorted(findings, key=lambda row: (row.policy, row.kind, row.path, row.line))


def check(root: Path, contracts: Contracts) -> list[Finding]:
    root = root.resolve()
    findings = []
    for policy in contracts.policies:
        for declaration in policy.declarations:
            findings.extend(declaration_findings(root, policy, declaration))
    findings.extend(stale_aliases(root, contracts.aliases))
    return sorted_findings(findings)


def counts(findings: Sequence[Finding]) -> dict[str, int]:
    counter = Counter(finding.kind for finding in findings)
    kinds = (cls.__dataclass_fields__["kind"].default for cls in FINDING_TYPES)
    return {kind: counter[kind] for kind in sorted(kinds)}


def json_report(findings: Sequence[Finding]) -> str:
    return json.dumps({"version": 1, "findings": [asdict(finding) for finding in findings],
                       "counts": counts(findings)}, ensure_ascii=False, indent=2)


def markdown_cell(value: object) -> str:
    return " ".join(str(value).split()).replace("|", "\\|")


def markdown_report(findings: Sequence[Finding]) -> str:
    lines = ["# Policy ownership (shadow)", "", "| Kind | Count |", "| --- | ---: |"]
    lines.extend(f"| {kind} | {count} |" for kind, count in counts(findings).items())
    lines.extend(("", "| Policy | Kind | Path | Line | Value | Owner value | Detail |",
                  "| --- | --- | --- | ---: | --- | --- | --- |"))
    for finding in findings:
        cells = (finding.policy, finding.kind, finding.path, finding.line,
                 finding.value, finding.owner_value, finding.detail)
        lines.append("| " + " | ".join(map(markdown_cell, cells)) + " |")
    return "\n".join(lines)


def exit_status(findings: Sequence[Finding], strict: bool) -> int:
    return int(strict and any(finding.kind in BLOCKING_KINDS for finding in findings))


def configure_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    configure_output()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--contracts", type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true")
    args = parser.parse_args(argv)
    if args.contracts is None:
        print("no contracts configured")
        return 0
    try:
        contracts = load_contracts(args.contracts.expanduser())
        findings = check(args.root.expanduser().resolve(), contracts)
    except (OSError, UnicodeError, ValueError, KeyError, TypeError, re.error) as error:
        print(f"contracts unreadable: {' '.join(str(error).splitlines())}", file=sys.stderr)
        return 2
    print(json_report(findings) if args.json else markdown_report(findings))
    return exit_status(findings, args.strict)


if __name__ == "__main__":
    raise SystemExit(main())
