#!/usr/bin/env python3
"""Machine guard (Windows): orphaned search processes, handle alarm, Docker sanity.

Origin: 2026-10-28, a `find /` from a Claude Code session stayed orphaned for 3 h (Bash's timeout sends the
command to the background without killing it), with 1.29 M handles and 1.24 GB of nonpaged pool, and the Docker
VM held 16 GB with 12 containers, 9 of them unhealthy for up to 20 h, left behind by validation sessions.

Usage: python -I tools/machine_guard.py hourly   # kills orphaned searches (>30 min, dead parent), handle
                                                 # and pool alarm, records vmmemWSL (runs in sync.sh)
       python -I tools/machine_guard.py weekly   # prunes containers stopped >24 h, build cache >7 d,
                                                 # dangling images; unhealthy >2 h goes to the inbox (weekly.sh)
       python -I tools/machine_guard.py report [--since YYYY-MM-DD]   # the 3 numbers of the weekly measurement
Events: ~/.claude/scripts/medicoes/eventos.jsonl (types orfao_morto, handles_alarme, vmmem_gb,
docker_podado, docker_unhealthy). Only acts on Windows; on another OS it exits 0 without touching anything.
"""
import argparse
import json
import os
import platform
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

EVENTOS = os.path.expanduser("~/.claude/scripts/medicoes/eventos.jsonl")
ORFAOS = {"find.exe", "grep.exe", "rg.exe", "fd.exe", "tree.exe", "du.exe"}
ORFAO_MIN = 30          # minutes alive with a dead parent
HANDLES_ALARME = 100_000
POOL_NP_ALARME_MB = 2048   # this machine (Hyper-V + WSL + Docker) idles at ~1.2 GB; the find pushed it to 1.24 GB
DOCKER_PARADO_H = 24
DOCKER_CACHE_D = 7
UNHEALTHY_H = 2


def log(tipo, **extra):
    try:
        os.makedirs(os.path.dirname(EVENTOS), exist_ok=True)
        with open(EVENTOS, "a", encoding="utf-8") as f:
            f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "sid": "machine_guard", "tipo": tipo,
                                **extra}, ensure_ascii=False) + "\n")
    except OSError:
        pass


def ps(script):
    """Run a PowerShell snippet and return stdout; empty if it fails."""
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                             capture_output=True, text=True, timeout=120, encoding="utf-8", errors="replace")
        return out.stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def inbox(titulo, detalhe):
    """Add one item to the decision inbox, without duplicating the title."""
    aqui = os.path.dirname(os.path.abspath(__file__))
    try:
        lista = subprocess.run([sys.executable, "-I", os.path.join(aqui, "decisions.py"), "list"],
                               capture_output=True, text=True, timeout=60, encoding="utf-8", errors="replace").stdout
        if titulo in lista:
            return
        subprocess.run([sys.executable, "-I", os.path.join(aqui, "decisions.py"), "add", titulo,
                        "--level", "superego", "--source", "machine_guard", "--detail", detalhe],
                       capture_output=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        pass


def processos():
    """[{pid, ppid, name, start_epoch, handles, cmd}] of live processes (Win32_Process + Get-Process)."""
    script = r"""
$alive = @{}; Get-Process | ForEach-Object { $alive[$_.Id] = $_.HandleCount }
Get-CimInstance Win32_Process | ForEach-Object {
  $cd = if ($_.CreationDate) { [int][double]::Parse(($_.CreationDate.ToUniversalTime() - (Get-Date '1970-01-01')).TotalSeconds) } else { 0 }
  $cl = if ($_.CommandLine) { $_.CommandLine.Substring(0, [Math]::Min(200, $_.CommandLine.Length)) } else { '' }
  [pscustomobject]@{ pid=$_.ProcessId; ppid=$_.ParentProcessId; name=$_.Name; start=$cd; handles=$alive[[int]$_.ProcessId]; cmd=$cl }
} | ConvertTo-Json -Compress
"""
    out = ps(script).strip()
    if not out:
        return []
    try:
        dados = json.loads(out)
    except ValueError:
        return []
    return dados if isinstance(dados, list) else [dados]


def hourly():
    procs = processos()
    vivos = {p["pid"] for p in procs}
    agora = time.time()
    mortos = []
    for p in procs:
        if p["name"] not in ORFAOS or p["ppid"] in vivos:
            continue
        idade_min = (agora - (p.get("start") or agora)) / 60
        if idade_min < ORFAO_MIN:
            continue
        ps(f"Stop-Process -Id {int(p['pid'])} -Force -ErrorAction SilentlyContinue")
        mortos.append(p)
        log("orfao_morto", pid=p["pid"], nome=p["name"], idade_min=round(idade_min), handles=p.get("handles"),
            cmd=p.get("cmd", ""))
        print(f"orphan killed: {p['name']} pid={p['pid']} age={idade_min:.0f}min handles={p.get('handles')} :: {p.get('cmd','')[:120]}")
    # Per-process handle alarm and nonpaged pool alarm.
    gordos = [p for p in procs if (p.get("handles") or 0) > HANDLES_ALARME and p["pid"] not in {m["pid"] for m in mortos}]
    pool = ps(r"[math]::Round((Get-Counter '\Memory\Pool Nonpaged Bytes').CounterSamples[0].CookedValue/1MB)").strip()
    pool_mb = int(pool) if pool.isdigit() else 0
    if gordos or pool_mb > POOL_NP_ALARME_MB:
        quem = ", ".join(f"{p['name']} pid={p['pid']} handles={p['handles']}" for p in gordos) or "no process above the ceiling"
        log("handles_alarme", processos=[{"pid": p["pid"], "nome": p["name"], "handles": p["handles"]} for p in gordos],
            pool_np_mb=pool_mb)
        inbox("Machine: kernel handles or pool above the ceiling",
              f"{quem}; nonpaged pool {pool_mb} MB (ceiling {POOL_NP_ALARME_MB}). See eventos.jsonl type handles_alarme.")
        print(f"alarm: {quem}; nonpaged pool {pool_mb} MB")
    # vmmemWSL: the week's peak goes to the measurement.
    vm = ps(r"(Get-Process vmmemWSL,vmmem -ErrorAction SilentlyContinue | Measure-Object WorkingSet64 -Sum).Sum").strip()
    try:
        gb = round(int(float(vm)) / 2**30, 1)
    except ValueError:
        gb = 0.0
    log("vmmem_gb", gb=gb, pool_np_mb=pool_mb, processos=len(procs))
    print(f"vmmem {gb} GB, nonpaged pool {pool_mb} MB, {len(procs)} processes, {len(mortos)} orphan(s) killed")


def docker(args):
    try:
        out = subprocess.run(["docker", *args], capture_output=True, text=True, timeout=600, encoding="utf-8",
                             errors="replace")
        return out.returncode, out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return 1, ""


def weekly():
    rc, _ = docker(["info", "--format", "{{.ServerVersion}}"])
    if rc != 0:
        print("docker not running, prune skipped")
        return
    podado = {}
    for nome, cmd in (("containers", ["container", "prune", "-f", "--filter", f"until={DOCKER_PARADO_H}h"]),
                      ("build_cache", ["builder", "prune", "-f", "--filter", f"until={DOCKER_CACHE_D * 24}h"]),
                      ("images", ["image", "prune", "-f"])):
        rc, out = docker(cmd)
        ultima = out.splitlines()[-1] if out else ""
        podado[nome] = ultima
        print(f"prune {nome}: {ultima or 'rc=' + str(rc)}")
    log("docker_podado", **podado)
    # Containers unhealthy for more than 2 h: does not remove them (may belong to a live session), warns instead.
    rc, out = docker(["ps", "--filter", "health=unhealthy", "--format", "{{.Names}}|{{.Status}}"])
    ruins = []
    for linha in out.splitlines():
        nome, _, status = linha.partition("|")
        horas = 0
        if "hour" in status:
            try:
                horas = int(status.split("Up ")[1].split(" hour")[0].replace("About an", "1"))
            except (IndexError, ValueError):
                horas = 1
        elif "day" in status:
            horas = 24
        if horas >= UNHEALTHY_H:
            ruins.append(f"{nome} ({status})")
    if ruins:
        log("docker_unhealthy", containers=ruins)
        inbox("Docker: containers unhealthy for more than 2 h",
              "; ".join(ruins) + ". Did the owning session end without cleaning up? Remove with docker rm -f or confirm it is in use.")
        print("unhealthy: " + "; ".join(ruins))


def report(since):
    """The 3 numbers of the weekly measurement: orphans killed, Docker prunes, vmmemWSL peak."""
    n_orfaos, n_podas, pico = 0, 0, 0.0
    if os.path.exists(EVENTOS):
        for linha in open(EVENTOS, encoding="utf-8"):
            try:
                e = json.loads(linha)
            except ValueError:
                continue
            if since and e.get("ts", "")[:10] < since:
                continue
            t = e.get("tipo")
            if t == "orfao_morto":
                n_orfaos += 1
            elif t == "docker_podado":
                n_podas += 1
            elif t == "vmmem_gb":
                pico = max(pico, float(e.get("gb") or 0))
    saida = {"orfaos_mortos": n_orfaos, "docker_podas": n_podas, "vmmem_pico_gb": pico}
    print(json.dumps(saida))
    return saida


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("modo", choices=["hourly", "weekly", "report"])
    ap.add_argument("--since")
    a = ap.parse_args()
    if a.modo == "report":
        report(a.since)
        return 0
    if platform.system() != "Windows":
        print("machine_guard: not Windows, nothing to do")
        return 0
    (hourly if a.modo == "hourly" else weekly)()
    return 0


if __name__ == "__main__":
    sys.exit(main())
