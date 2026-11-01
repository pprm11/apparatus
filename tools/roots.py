#!/usr/bin/env python3
"""Where the layer repos live: one resolver, no hardcoded folder.

The layers root is the folder that holds the layer checkouts side by side (superego, psique, id-context,
and so on). Order of precedence:

  1. the explicit `--root DIR` flag
  2. the PSIQUE_ROOT environment variable
  3. the folder that contains this superego checkout (clone it anywhere and it just works)

Everything else derives from the root: the manifest is `<root>/psique/manifest.json` unless `--manifest` or
SYNC_MANIFEST says otherwise, and a layer path in a manifest may be relative to the root. Absolute paths and
`~/...` paths in an existing manifest keep working unchanged.

  python -I tools/roots.py [--root DIR]     # print the resolved root
"""
import argparse
import os
from pathlib import Path

ENV = "PSIQUE_ROOT"


def checkout_parent() -> str:
    """Folder holding the superego checkout this file belongs to."""
    return str(Path(__file__).resolve().parent.parent.parent)


def layers_root(explicit: str | None = None, environ: dict | None = None) -> str:
    env = (os.environ if environ is None else environ).get(ENV, "")
    chosen = explicit or env or checkout_parent()
    return os.path.normpath(os.path.expanduser(chosen))


def default_manifest(explicit_root: str | None = None, environ: dict | None = None) -> str:
    return os.path.join(layers_root(explicit_root, environ), "psique", "manifest.json")


def resolve_layer_path(path: str, root: str) -> str:
    """A manifest layer path: absolute and ~ paths stay, relative ones hang off the layers root."""
    expanded = os.path.expanduser(path)
    return os.path.normpath(expanded if os.path.isabs(expanded) else os.path.join(root, expanded))


def main() -> int:
    ap = argparse.ArgumentParser(description="Print the resolved layers root.")
    ap.add_argument("--root")
    print(layers_root(ap.parse_args().root))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
