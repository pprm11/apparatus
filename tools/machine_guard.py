#!/usr/bin/env python3
"""Guarda da máquina (Windows): processos órfãos de busca, alarme de handles, sanidade do Docker.

Origem: 28/10/2026, um `find /` de uma sessão do Claude Code ficou 3 h órfão (o timeout do Bash manda o
comando ao background sem matar), com 1,29 M handles e 1,24 GB de pool não paginado, e a VM do Docker
segurava 16 GB com 12 containers, 9 deles unhealthy há até 20 h, deixados por sessões de validação.

Usage: python -I tools/machine_guard.py hourly   # mata órfãos de busca (>30 min, pai morto), alarme de
                                                 # handles e pool, registra vmmemWSL (roda em sync.sh)
       python -I tools/machine_guard.py weekly   # prune de containers parados >24 h, build cache >7 d,
                                                 # imagens soltas; unhealthy >2 h vai ao inbox (weekly.sh)
       python -I tools/machine_guard.py report [--since AAAA-MM-DD]   # os 3 números da medição semanal
Eventos: ~/.claude/scripts/medicoes/eventos.jsonl (tipos orfao_morto, handles_alarme, vmmem_gb,
docker_podado, docker_unhealthy). Só faz algo no Windows; em outro SO sai com 0 sem tocar em nada.
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
ORFAO_MIN = 30          # minutos vivo com o pai morto
HANDLES_ALARME = 100_000
POOL_NP_ALARME_MB = 2048   # esta máquina (Hyper-V + WSL + Docker) fica em ~1,2 GB em repouso; o find levou a 1,24 GB
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
    """Roda um trecho de PowerShell e devolve stdout; vazio se falhar."""
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
                             capture_output=True, text=True, timeout=120, encoding="utf-8", errors="replace")
        return out.stdout
    except (OSError, subprocess.SubprocessError):
        return ""


def inbox(titulo, detalhe):
    """Um item na caixa de decisões, sem duplicar o título."""
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
    """[{pid, ppid, name, start_epoch, handles, cmd}] dos processos vivos (Win32_Process + Get-Process)."""
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
    # Alarme de handles por processo e de pool não paginado.
    gordos = [p for p in procs if (p.get("handles") or 0) > HANDLES_ALARME and p["pid"] not in {m["pid"] for m in mortos}]
    pool = ps(r"[math]::Round((Get-Counter '\Memory\Pool Nonpaged Bytes').CounterSamples[0].CookedValue/1MB)").strip()
    pool_mb = int(pool) if pool.isdigit() else 0
    if gordos or pool_mb > POOL_NP_ALARME_MB:
        quem = ", ".join(f"{p['name']} pid={p['pid']} handles={p['handles']}" for p in gordos) or "nenhum processo acima do teto"
        log("handles_alarme", processos=[{"pid": p["pid"], "nome": p["name"], "handles": p["handles"]} for p in gordos],
            pool_np_mb=pool_mb)
        inbox("Máquina: handles ou pool do kernel acima do teto",
              f"{quem}; pool não paginado {pool_mb} MB (teto {POOL_NP_ALARME_MB}). Ver eventos.jsonl tipo handles_alarme.")
        print(f"alarm: {quem}; nonpaged pool {pool_mb} MB")
    # vmmemWSL: pico da semana vai para a medição.
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
    # Containers unhealthy há mais de 2 h: não derruba (pode ser de uma sessão viva), avisa.
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
        inbox("Docker: containers unhealthy há mais de 2 h",
              "; ".join(ruins) + ". Sessão dona terminou sem baixar? Remova com docker rm -f ou confirme o uso.")
        print("unhealthy: " + "; ".join(ruins))


def report(since):
    """Os 3 números da medição semanal: órfãos mortos, podas do Docker, pico de vmmemWSL."""
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
