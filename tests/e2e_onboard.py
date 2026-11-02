"""End-to-end run of the documented install for a second person, through the real entry script of this OS.

  python -I tests/e2e_onboard.py [--register-jobs]

Fresh temporary HOME, shared layers as bare repos on disk, `install.sh` (macOS, Linux) or `install.ps1` (Windows)
-> `init` -> `doctor` -> `update` -> `uninstall`. With --register-jobs the scheduled job is really registered with
this OS's scheduler, checked by the doctor, and removed again by `uninstall` (CI runners are disposable; do not
use it on a machine you care about). Not collected by `unittest discover` (the name does not start with test_).
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_onboard import CANARY_COMPANY, CANARY_ID, GIT_ENV, make_shared  # noqa: E402


def entry(*args: str) -> list[str]:
    if os.name == "nt":
        return ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "install.ps1"), *args]
    return ["sh", str(ROOT / "install.sh"), *args]


def run(env: dict, *args: str) -> str:
    res = subprocess.run(entry(*args), env=env, capture_output=True, text=True, encoding="utf-8")
    print(f"$ install {' '.join(args[:2])} -> {res.returncode}\n{res.stdout}{res.stderr}")
    if res.returncode:
        raise SystemExit(f"FAILED: install {args[0]} exited {res.returncode}")
    return res.stdout


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--register-jobs", action="store_true")
    args = ap.parse_args()
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp).resolve()
        home, remote = base / "home", base / "remote"
        home.mkdir()
        os.environ.update(GIT_ENV)
        coll = make_shared(remote, "owner", "collective-teamx", {
            "level": "collective", "name": "teamx", "mode": "readonly", "globals": ["glossary.md"], "rules": [],
            "dirs": [], "files": [], "company": "teamx"}, {"global/glossary.md": "# Glossary\n\n- **term-a**: shared.\n"})
        make_shared(remote, "owner", "id", {"level": "id", "globals": ["g.md"], "rules": [], "dirs": [],
                    "files": []}, {"global/g.md": f"{CANARY_ID}\n"})
        make_shared(remote, "owner", "ego-" + "na" + "mastex", {"level": "ego", "name": "o", "globals": ["g.md"],
                    "rules": [], "dirs": [], "files": []}, {"global/g.md": f"{CANARY_COMPANY}\n"})
        env = dict(os.environ, HOME=str(home), USERPROFILE=str(home), SUPEREGO_HOME=str(base / "state"))
        for k in ("CLAUDE_CONFIG_DIR", "CODEX_HOME", "COMPANIES_FILE"):
            env.pop(k, None)
        run(env, "init", "--name", "Test Person", "--github", "testperson", "--yes", "--git-host", f"local:{remote}",
            "--jobs", "apply" if args.register_jobs else "plan", "--layer", f"collective:teamx={coll}",
            "--root", "teamx=~/Work/teamx")
        doctor_out = run(env, "doctor")
        assert "0 failed" in doctor_out, doctor_out
        if args.register_jobs:
            assert "job-update: registrado" in doctor_out, "the scheduled job is not registered:\n" + doctor_out
        agents = (home / ".codex" / "AGENTS.md").read_text(encoding="utf-8")
        claude = (home / ".claude" / "CLAUDE.md").read_text(encoding="utf-8")
        assert "teamx" in agents and "glossary.md" in claude and "glossario-teamx.md" in claude
        for name in (CANARY_ID, CANARY_COMPANY):
            for p in home.rglob("*"):
                if p.is_file() and ".git" not in p.parts:
                    assert name not in p.read_text(encoding="utf-8", errors="ignore"), f"{name} reached {p}"
        run(env, "update", "--push")
        manifest = json.loads((home / "Codes" / "self" / "manifest.json").read_text(encoding="utf-8"))
        assert [l["level"] for l in manifest["layers"]] == ["superego", "collective", "ego", "id"]
        shutil.copy(home / "Codes" / "self" / "manifest.json", base / "m.json")
        run(env, "uninstall", "--dry-run")
        assert (home / ".claude" / "glossary.md").exists(), "dry-run must change nothing"
        run(env, "uninstall")
        assert not (home / ".claude" / "glossary.md").exists()
        if args.register_jobs:
            sys.path.insert(0, str(ROOT / "tools"))
            import scheduler  # noqa: PLC0415
            left = scheduler.backend_for().status(scheduler.jobs_for(base / "m.json", all_jobs=True))
            assert not any(left.values()), f"jobs still registered after uninstall: {left}"
    print("OK: install, doctor, update and uninstall passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
