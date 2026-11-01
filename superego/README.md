# Superego layer

This folder holds the superego layer, the universal agent context.

- `layer.json` declares the files owned by this layer.
- `global/` holds universal agent rules and the glossary.
- `rules/` holds rules loaded into every session.
- `harness/` holds harness adapters and the skill manifest.
- `skills/` holds generic skills loaded when needed.
- `scripts/` holds hooks and supporting scripts.

These files are loaded into agent context. Keep them short and within the byte budget.
Check the budget with `tools/context_budget.py` at the repository root.
Only rules valid for anyone belong here. See [Governance](../GOVERNANCE.md).
