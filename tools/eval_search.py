#!/usr/bin/env python3
"""Measure local memory search: hit@1, hit@3 and the rank of each expected file.

Two sets: evals/search_cases.json (the keywords were written knowing these) and
evals/search_cases_holdout.json (written afterwards, never tuned against).

Usage: python -I tools/eval_search.py [--root ~/.claude]
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # -I drops the script dir from sys.path
from search_memory import resolve_root, search  # noqa: E402

def evals_dir() -> str:
    """evals/ of the active ego layer (the cases query that company's memory); EVALS_DIR overrides."""
    if os.environ.get("EVALS_DIR"):
        return os.environ["EVALS_DIR"]
    manifest = os.environ.get("SYNC_MANIFEST", os.path.expanduser("~/Codes/psique/manifest.json"))
    try:
        import json
        with open(manifest, encoding="utf-8") as fh:
            for layer in json.load(fh)["layers"]:
                if layer["level"] == "ego" and layer.get("active", True):
                    return os.path.join(os.path.expanduser(layer["path"]), "evals")
    except (OSError, ValueError, KeyError):
        pass
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "evals")


EVALS = evals_dir()
SETS = ("search_cases.json", "search_cases_holdout.json")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=None)
    args = ap.parse_args()
    try:
        args.root = resolve_root(args.root)
    except (OSError, ValueError, KeyError) as exc:
        ap.error(str(exc))
    for name in SETS:
        with open(os.path.join(EVALS, name), encoding="utf-8") as fh:
            cases = json.load(fh)
        top1 = top3 = 0
        print(f"## {name}")
        for case in cases:
            names = [h.doc.name for h in search(case["query"], args.root, 10)]
            rank = names.index(case["expect"]) + 1 if case["expect"] in names else None
            top1 += rank == 1
            top3 += rank is not None and rank <= 3
            print(f"{rank or '-':>2}  {case['query']}")
        print(f"hit@1 {top1} de {len(cases)} · hit@3 {top3} de {len(cases)}\n")

if __name__ == "__main__":
    main()
