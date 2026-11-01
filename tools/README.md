# tools/

The Python tooling of the program. The superego layer lives in `superego/`. Each file is a command line entry point run as `python -I tools/<name>.py`.

- Layers and install: `layers.py` (export and pull), `compose.py` (builds `CLAUDE.md`), `render_harness.py`
  (builds the Codex `AGENTS.md`), `onboard.py` (install, update, doctor, uninstall), `bootstrap.py`, `migrate.py`.
- Memory and learning: `search_memory.py`, `lint_memory.py`, `lint_glossary.py`, `decay.py`, `harvest.py`, `learn.py`.
- Safety: `privacy.py`, `redact.py`, `secret_gate.py`, `push_guard.py`, `secrets_backup.py`.
- Operations: `scheduler.py`, `run_job.py`, `decisions.py`, `delegate.py`, `doctor.py`.

The commands and flags that other layers rely on are listed in `docs/contract.md`. Every tool has `--help`.
Tests live in `tests/`.
