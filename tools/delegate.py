#!/usr/bin/env python3
"""Run a child agent in the other harness: Claude Code orchestrates Codex children and vice versa (B20).

  python -I tools/delegate.py run --brief-file brief.md [--to codex|claude] [--cwd DIR] [--tier cheap|mid|top]
                                  [--write] [--timeout 30] [--budget 2] [--background]
  python -I tools/delegate.py status <run-id>      # done/running, exit code, last message, diff stat
  python -I tools/delegate.py list                 # recent runs

--to defaults to the other harness (Claude Code sets CLAUDECODE in its shell). --write gives the child its
own git worktree on branch delegate/<run-id>, so it never edits the orchestrator's checkout; without it the
child is read-only. Children cannot delegate again (DELEGATE_DEPTH). Every run keeps brief, command, log,
final message and diff stat in ~/Codes/superego/runs/<run-id>/ (not committed).

Cost ceilings: a Claude child gets --max-budget-usd (default by tier); Codex has no budget flag, so the
ceiling there is --timeout.
"""
import argparse
import glob
import json
import os
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import require_codex  # noqa: E402

RUNS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "runs")
CLAUDE_MODEL = {"cheap": "haiku", "mid": "sonnet", "top": "opus"}
CODEX_EFFORT = {"cheap": "low", "mid": "medium", "top": "high"}
CLAUDE_BUDGET = {"cheap": 0.5, "mid": 2.0, "top": 5.0}
PREAMBLE = """You are a child agent. An orchestrator session in another coding harness dispatched you with the brief
below. Rules: do only what the brief asks; do not start other agents or sessions; do not commit, push, merge or
open PRs unless the brief says so; stay inside the working directory. Finish with a short report:
status (done | blocked), files changed, how you verified it, open questions.

--- BRIEF ---
"""


def caller() -> str:
    return "claude" if os.environ.get("CLAUDECODE") else "codex"


def build_command(to: str, cwd: str, tier: str, write: bool, budget: float, last: str) -> list[str]:
    """argv for the child; the prompt goes on stdin."""
    if to == "codex":
        # --ephemeral: the child's thread stays out of the user's Codex session list
        return [require_codex(), "exec", "-C", cwd, "--skip-git-repo-check", "--ephemeral",
                "-s", "workspace-write" if write else "read-only",
                "-c", f"model_reasoning_effort={CODEX_EFFORT[tier]}", "-o", last, "-"]
    # A read-only child may inspect git state and list files, nothing else; Bash is open only when it can write.
    tools = (["Read", "Glob", "Grep", "Bash", "Edit", "Write"] if write else
             ["Read", "Glob", "Grep", "Bash(git diff:*)", "Bash(git log:*)", "Bash(git show:*)", "Bash(ls:*)"])
    return ["claude", "-p", "--model", CLAUDE_MODEL[tier], "--max-budget-usd", str(budget),
            "--permission-mode", "acceptEdits" if write else "default",
            "--allowedTools", *tools, "--output-format", "text"]


def make_worktree(cwd: str, run_id: str) -> str:
    root = subprocess.run(["git", "-C", cwd, "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True).stdout.strip()
    path = os.path.join(os.path.dirname(root), ".worktrees", f"{os.path.basename(root)}-{run_id}")
    subprocess.run(["git", "-C", root, "worktree", "add", "-b", f"delegate/{run_id}", path], capture_output=True, text=True, check=True)
    return path


def git_status(cwd: str) -> list[str]:
    """`git status --short` lines; the run reports only what changed against the snapshot taken at start."""
    res = subprocess.run(["git", "-C", cwd, "status", "--short"], capture_output=True, text=True)
    return res.stdout.splitlines() if res.returncode == 0 else []


def execute(run_dir: str) -> int:
    with open(os.path.join(run_dir, "run.json"), encoding="utf-8") as fh:
        run = json.load(fh)
    with open(os.path.join(run_dir, "brief.md"), encoding="utf-8") as fh:
        prompt = PREAMBLE + fh.read()
    env = {**os.environ, "DELEGATE_DEPTH": "1"}
    if run["to"] == "claude":
        env.pop("ANTHROPIC_API_KEY", None)  # subscription login, never per-token billing
        env.pop("CLAUDECODE", None)
    last = os.path.join(run_dir, "last.md")
    started = time.time()
    with open(os.path.join(run_dir, "log.txt"), "w", encoding="utf-8") as log:
        try:
            proc = subprocess.run(run["argv"], input=prompt, text=True, encoding="utf-8", cwd=run["cwd"], env=env,
                                  stdout=subprocess.PIPE if run["to"] == "claude" else log, stderr=log,
                                  timeout=run["timeout_min"] * 60)
            code = proc.returncode
            if run["to"] == "claude":
                with open(last, "w", encoding="utf-8") as fh:
                    fh.write(proc.stdout or "")
        except subprocess.TimeoutExpired:
            code = 124
            log.write(f"\ntimeout after {run['timeout_min']} min\n")
    after = git_status(run["cwd"])
    result = {"exit": code, "minutes": round((time.time() - started) / 60, 1),
              "changed": [line for line in after if line not in set(run.get("before", []))]}
    with open(os.path.join(run_dir, "result.json"), "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=1)
    return code


def start(args: argparse.Namespace) -> str:
    if int(os.environ.get("DELEGATE_DEPTH", "0")) >= 1:
        raise SystemExit("refused: a child agent cannot delegate again (depth 1)")
    to = args.to or ("codex" if caller() == "claude" else "claude")
    run_id = time.strftime("%Y%m%d-%H%M%S")
    run_dir = os.path.join(RUNS, run_id)
    os.makedirs(run_dir)
    brief = args.brief if args.brief else open(args.brief_file, encoding="utf-8").read()
    with open(os.path.join(run_dir, "brief.md"), "w", encoding="utf-8") as fh:
        fh.write(brief)
    cwd = os.path.abspath(args.cwd)
    if args.write:
        cwd = make_worktree(cwd, run_id)
    budget = args.budget or CLAUDE_BUDGET[args.tier]
    run = {"id": run_id, "to": to, "from": caller(), "cwd": cwd, "tier": args.tier, "write": args.write,
           "timeout_min": args.timeout, "budget_usd": budget if to == "claude" else None, "before": git_status(cwd),
           "argv": build_command(to, cwd, args.tier, args.write, budget, os.path.join(run_dir, "last.md"))}
    with open(os.path.join(run_dir, "run.json"), "w", encoding="utf-8") as fh:
        json.dump(run, fh, indent=1)
    if args.background:
        flags = (subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP) if os.name == "nt" else 0
        subprocess.Popen([sys.executable, "-I", os.path.abspath(__file__), "_exec", run_dir],
                         creationflags=flags, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        execute(run_dir)
    return run_id


def status(run_id: str) -> str:
    run_dir = os.path.join(RUNS, run_id)
    with open(os.path.join(run_dir, "run.json"), encoding="utf-8") as fh:
        run = json.load(fh)
    lines = [f"{run_id}: {run['from']} -> {run['to']} · tier {run['tier']} · {'write' if run['write'] else 'read-only'} · {run['cwd']}"]
    res_path = os.path.join(run_dir, "result.json")
    if not os.path.isfile(res_path):
        return "\n".join(lines + ["running"])
    with open(res_path, encoding="utf-8") as fh:
        res = json.load(fh)
    lines.append(f"exit {res['exit']} in {res['minutes']} min · {len(res['changed'])} files changed")
    lines += [f"  {c}" for c in res["changed"][:30]]
    last = os.path.join(run_dir, "last.md")
    if os.path.isfile(last):
        with open(last, encoding="utf-8") as fh:
            lines += ["--- final message ---", fh.read().strip()]
    return "\n".join(lines)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_run = sub.add_parser("run")
    src = p_run.add_mutually_exclusive_group(required=True)
    src.add_argument("--brief-file")
    src.add_argument("--brief")
    p_run.add_argument("--to", choices=("codex", "claude"))
    p_run.add_argument("--cwd", default=".")
    p_run.add_argument("--tier", choices=tuple(CLAUDE_MODEL), default="mid")
    p_run.add_argument("--write", action="store_true")
    p_run.add_argument("--timeout", type=int, default=30, help="minutes")
    p_run.add_argument("--budget", type=float, help="USD, Claude children only")
    p_run.add_argument("--background", action="store_true")
    p_status = sub.add_parser("status")
    p_status.add_argument("id")
    sub.add_parser("list")
    p_exec = sub.add_parser("_exec")
    p_exec.add_argument("run_dir")
    args = ap.parse_args()

    if args.cmd == "run":
        run_id = start(args)
        print(status(run_id) if not args.background else f"started {run_id}; check: delegate.py status {run_id}")
    elif args.cmd == "status":
        print(status(args.id))
    elif args.cmd == "list":
        for d in sorted(glob.glob(os.path.join(RUNS, "*")))[-15:]:
            print(status(os.path.basename(d)).splitlines()[0])
    elif args.cmd == "_exec":
        return execute(args.run_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
