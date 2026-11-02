# Linux, Windows and macOS

The context tooling is written to run on the three systems. This page says what is shared, what is per OS and
what is still pending.

## Shared

- One entry point per task, in Python, with `pathlib` and `subprocess` without a shell:
  `tools/bootstrap.py`, `tools/doctor.py`, `tools/scheduler.py`, `tools/run_job.py`.
- `bootstrap.sh` (macOS, Linux) and `bootstrap.ps1` (Windows) only find a real Python 3.10+ and hand over.
- Every OS-specific rule is a pure function of (platform, environment, home) in `tools/ospaths.py`,
  `tools/keyfile.py` and `tools/scheduler.py`, so `tests/test_cross_os.py` checks all three systems on any
  machine. CI runs it on `ubuntu-latest`, `windows-latest` and `macos-latest` (job `cross-os`).

## Per OS

| Concern | Windows | macOS | Linux |
|---|---|---|---|
| Packages | winget | Homebrew | apt (other distros: the doctor prints the manual command) |
| Scheduler | Task Scheduler, `pythonw` (no console) | LaunchAgent in `~/Library/LaunchAgents` | systemd user timer; cron when systemd is not usable |
| Missed run | `StartWhenAvailable` | runs at next wake (launchd calendar interval) | `Persistent=true` |
| Key file | `icacls` rewrites the ACL | mode 0600 | mode 0600 |
| Desktop app sessions | `%APPDATA%\Claude\claude-code-sessions` | `~/Library/Application Support/Claude/...` | `$XDG_CONFIG_HOME/Claude/...` (unverified) |
| Codex skill links | directory junction (no admin) | symlink | symlink |

## Bootstrap

    ./bootstrap.sh --self OWNER/REPO --dry-run        # macOS, Linux
    .\bootstrap.ps1 --self OWNER/REPO --dry-run       # Windows

Stages: packages, vault, auth, repos, restore, jobs (opt-in with `--with-jobs`), doctor. Each stage checks
before it acts. The vault login is the only prompt on the happy path. Not automatable: the Claude Code and
Codex logins, the AWS SSO browser step, Docker Desktop virtualization and a possible reboot, and OAuth of MCP
servers (the bootstrap prints this list at the end).

## Scheduled jobs

    python -I tools/scheduler.py plan    --manifest MANIFEST
    python -I tools/scheduler.py install --manifest MANIFEST --apply [--replace-legacy]
    python -I tools/scheduler.py status  --manifest MANIFEST

Job names are `superego-<manifest id>-<job>`. `--replace-legacy` (Windows) removes the old `ClaudeContext*`
tasks after the new ones are registered. Nothing registers without `--apply`.

## Pending

- The jobs still run the bash scripts (`sync.sh`, `harvest.sh`, `weekly.sh`) through `tools/run_job.py`. They
  use bash 4 features (`mapfile`, `declare -A`) and GNU `timeout`, `date -d`, `find -mmin`, so on macOS they
  need a Homebrew bash with coreutils until they are ported to Python. `doctor` reports the bash version.
- The macOS and Linux app-session folders and the Codex binary lookup outside Windows are unverified on real
  machines; the doctor warns instead of failing.
- Hooks in `settings.json` are not rewritten yet: the doctor flags a bare `python` and a missing interpreter.
