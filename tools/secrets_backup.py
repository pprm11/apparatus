#!/usr/bin/env python3
"""Automatic encrypted backup of secret files with an age PUBLIC key: encrypting needs no unlock and no secret.

  secrets_backup.py scan [--add]          find secret files (no model); --add appends new paths to the manifest
  secrets_backup.py status                manifest paths vs last backup: ok | changed | new | removed
  secrets_backup.py backup [--commit] [--push]   encrypt files whose sha256 changed into <id layer>/sealed/secrets
  secrets_backup.py run [--commit] [--push] [--full-scan]   scan --add (at most every SECRETS_SCAN_HOURS, default 6)
                                          + backup + inbox items: the hourly entry point
  secrets_backup.py restore [--identity F] [--force]   decrypt everything to the original paths (needs the private key)

Layout in <id layer>/sealed/secrets: <id>.age (one per file, id = sha256(path)[:16], so file names leak nothing)
and manifest.json.age (path, sha256 of the plaintext, size, removed flag; encrypted too).
Local state ~/.claude/state/secrets-hashes.json holds paths and hashes only, never values.
Removed files are flagged and kept in the backup; nothing is ever deleted from it or from the manifest.
Output lists paths and counts only. Env: SECRETS_DEST (default: the id layer of the self manifest), AGE_RECIPIENT or ~/.config/id-context/recipient,
AGE_IDENTITY, SECRETS_INCLUDE_CODEX_AUTH=1, and for tests AGE_CMD, SECRETS_HOME/STATE/MANIFEST, SECRETS_DECISIONS_CMD.
"""
import argparse, datetime, hashlib, json, os, shlex, shutil, subprocess, sys, time

import importlib.util

_roots_spec = importlib.util.spec_from_file_location("roots", os.path.join(os.path.dirname(__file__), "roots.py"))
roots = importlib.util.module_from_spec(_roots_spec)
_roots_spec.loader.exec_module(roots)

HOME = os.environ.get("SECRETS_HOME") or os.path.expanduser("~")
STATE_DIR = os.environ.get("SECRETS_STATE") or os.path.join(HOME, ".claude", "state")
HASHES = os.path.join(STATE_DIR, "secrets-hashes.json")
MANIFEST = os.environ.get("SECRETS_MANIFEST") or os.path.join(HOME, ".claude", "scripts", "secrets-manifest.txt")
RECIPIENT_FILES = [os.environ["AGE_RECIPIENTS_FILE"]] if os.environ.get("AGE_RECIPIENTS_FILE") else [
    os.path.join(HOME, ".config", "id-context", "recipient"),  # legacy folder name, kept so existing recipients keep working
    os.path.join(STATE_DIR, "age-recipients.txt")]
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # apparatus (or its worktree)
AGE = shlex.split(os.environ.get("AGE_CMD", "age"))
AGE[0] = shutil.which(AGE[0]) or AGE[0]
DECISIONS = shlex.split(os.environ.get("SECRETS_DECISIONS_CMD", f'python -I "{REPO}/tools/decisions.py"'))
MAX_BYTES = 1_000_000
DOTDIRS = (".ssh", ".aws")  # more home folders: one "~/.name" per line in scripts/secrets-scan-dirs.txt (id layer)
SCAN_DIRS_FILE = os.path.join(os.path.dirname(MANIFEST), "secrets-scan-dirs.txt")
PRUNE = {"node_modules", ".git", "__pycache__", "site-packages", ".mypy_cache", ".ruff_cache", ".pytest_cache",
         ".venv", "venv", ".deps", ".claude"}
PUBLIC_NAMES = {"cacert.pem", "ca-bundle.pem", "cert.pem.example"}  # public CA bundles, not secrets
SCAN_HOURS = float(os.environ.get("SECRETS_SCAN_HOURS", "6"))  # full walk of ~/Codes costs ~1 min
EXAMPLE = (".example", ".sample", ".template", ".dist")
CRED_EXT = {"json", "csv", "txt", "ini", "yaml", "yml", "toml"}


def fwd(p):
    return p.replace("\\", "/")


def rel(path):
    p, h = fwd(path), fwd(HOME)
    return "~" + p[len(h):] if p.startswith(h + "/") else p


def absolute(r):
    return HOME + r[1:] if r.startswith("~") else r


def sha(data):
    return hashlib.sha256(data).hexdigest()


def is_secret(name):
    low = name.lower()
    if low in PUBLIC_NAMES:
        return False
    if low == ".env" or (low.startswith(".env.") and not low.endswith(EXAMPLE)):
        return True
    if low.endswith((".pem", ".key")):
        return True
    if low.startswith("id_") and "." not in low:
        return True
    if low == "pgpw.txt":
        return True
    return low == "credentials" or (low.startswith("credentials.") and low.rsplit(".", 1)[1] in CRED_EXT)


def tracked(path):
    r = subprocess.run(["git", "-C", os.path.dirname(path), "ls-files", "--error-unmatch", os.path.basename(path)],
                       capture_output=True)
    return r.returncode == 0


def walk(root, skip):
    for d, dirs, files in os.walk(root):
        dirs[:] = [x for x in dirs if x not in PRUNE and not x.startswith(("venv-", ".venv-"))
                   and not (skip and fwd(os.path.join(d, x)).startswith(skip))]
        for f in files:
            if is_secret(f):
                yield os.path.join(d, f)


def scan(dest=None):
    """-> (found: sorted rel paths, skipped: [(rel, reason)])."""
    skip = fwd(os.path.realpath(dest)) if dest else None
    extra = []
    if os.path.isfile(SCAN_DIRS_FILE):
        extra = [l.strip()[2:] for l in open(SCAN_DIRS_FILE, encoding="utf-8")
                 if l.strip().startswith("~/") and not l.lstrip().startswith("#")]
    roots = [os.path.join(HOME, "Codes")] + [os.path.join(HOME, x) for x in (*DOTDIRS, *extra)]
    found, skipped = set(), []
    for root in roots:
        if not os.path.isdir(root):
            continue
        for p in walk(root, skip):
            if os.path.getsize(p) > MAX_BYTES:
                skipped.append((rel(p), "over 1 MB")); continue
            if tracked(p):
                skipped.append((rel(p), "tracked by git")); continue
            found.add(rel(p))
    if os.environ.get("SECRETS_INCLUDE_CODEX_AUTH") == "1":
        cdir = os.path.join(HOME, ".codex")
        if os.path.isdir(cdir):
            found.update(rel(os.path.join(cdir, f)) for f in os.listdir(cdir)
                         if f.startswith("auth") and os.path.isfile(os.path.join(cdir, f)))
    return sorted(found), skipped


def manifest_paths():
    if not os.path.isfile(MANIFEST):
        return []
    return [l.strip() for l in open(MANIFEST, encoding="utf-8") if l.strip() and not l.lstrip().startswith("#")]


def add_to_manifest(paths):
    os.makedirs(os.path.dirname(MANIFEST), exist_ok=True)
    with open(MANIFEST, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(f"\n# auto-added {datetime.date.today()} by tools/secrets_backup.py\n")
        fh.writelines(p + "\n" for p in paths)


def load_state():
    try:
        return json.load(open(HASHES, encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(state):
    os.makedirs(STATE_DIR, exist_ok=True)
    json.dump(state, open(HASHES, "w", encoding="utf-8"), indent=1, sort_keys=True)


def recipients():
    raw = os.environ.get("AGE_RECIPIENT", "").replace(",", " ").split()
    for f in RECIPIENT_FILES:
        if not raw and os.path.isfile(f):
            raw = [l.strip() for l in open(f, encoding="utf-8") if l.strip() and not l.startswith("#")]
    bad = [r for r in raw if not r.startswith("age1")]
    if not raw or bad:
        raise SystemExit("no valid age public key: set AGE_RECIPIENT or put the age1... line in " + fwd(RECIPIENT_FILES[0]))
    return raw


def age(args, data=None):
    p = subprocess.run(AGE + args, input=data, capture_output=True)
    if p.returncode != 0:
        raise RuntimeError("age failed: " + p.stderr.decode("utf-8", "replace").strip()[:160])
    return p.stdout


def sealed_dir(dest):
    """Only the id layer repo (private) may receive the backup: never superego or ego, which are shared."""
    real, repo = fwd(os.path.realpath(dest)), fwd(os.path.realpath(REPO))
    if real == repo or real.startswith(repo + "/") or repo.startswith(real + "/"):
        raise SystemExit("SECRETS_DEST must not be the superego repo (or contain it)")
    try:
        level = json.load(open(os.path.join(dest, "layer.json"), encoding="utf-8")).get("level")
    except (OSError, ValueError):
        level = None
    if level != "id":
        raise SystemExit("SECRETS_DEST must be the id layer repo (layer.json level 'id'); got " + repr(level))
    return os.path.join(dest, "sealed", "secrets")


def default_dest():
    """SECRETS_DEST, else the active id layer of the self manifest."""
    if os.environ.get("SECRETS_DEST"):
        return os.environ["SECRETS_DEST"]
    man = os.environ.get("SYNC_MANIFEST") or roots.default_manifest()
    try:
        for l in json.load(open(man, encoding="utf-8"))["layers"]:
            if l["level"] == "id" and l.get("active", True):
                return absolute(l["path"])
    except (OSError, ValueError, KeyError):
        pass
    return None


def identity_from_bw(name):
    """Fetch the age private key from the vault into a private temp file; the caller deletes the folder."""
    import tempfile
    if not os.environ.get("BW_SESSION") and os.path.isfile(os.path.join(HOME, ".bw-session")):
        os.environ["BW_SESSION"] = open(os.path.join(HOME, ".bw-session")).read().strip()
    if not os.environ.get("BW_SESSION"):
        raise SystemExit('vault locked: run  export BW_SESSION="$(bw unlock --raw)"')
    cmd = shlex.split(os.environ.get("VAULT_BW_CMD", "bw"))
    cmd[0] = shutil.which(cmd[0]) or cmd[0]
    p = subprocess.run(cmd + ["get", "notes", name], capture_output=True, env=os.environ)
    if p.returncode != 0 or b"AGE-SECRET-KEY-" not in p.stdout:
        raise SystemExit(f"vault note '{name}' not found or has no age key")
    folder = tempfile.mkdtemp(prefix="age-id-")
    path = os.path.join(folder, "identity.txt")
    with open(path, "wb") as fh:
        fh.write(p.stdout)
    return path


def inbox(title, detail, options=None):
    """One open inbox item per title (same check as sync.sh); an inbox problem never fails the backup."""
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    try:
        listing = subprocess.run(DECISIONS + ["list"], capture_output=True, env=env).stdout or b""
        if title in listing.decode("utf-8", "replace"):
            return
        cmd = DECISIONS + ["add", title, "--detail", detail, "--source", "secrets_backup", "--level", "id"]
        if options:
            cmd += ["--options", *options]
        subprocess.run(cmd, capture_output=True, env=env)
    except Exception:
        print("inbox add failed")


def backup(dest, do_commit=False, do_push=False):
    """-> (counts dict, failed [(path, msg)], removed [path])."""
    out_dir = sealed_dir(dest)
    os.makedirs(out_dir, exist_ok=True)
    rcp = [a for r in recipients() for a in ("-r", r)]
    state = load_state()
    counts, failed, removed, dirty = {"encrypted": 0, "unchanged": 0}, [], [], False
    for p in manifest_paths():
        f = absolute(p)
        ent = state.get(p, {})
        if not os.path.isfile(f):
            if ent:
                removed.append(p)
                if not ent.get("removed"):
                    ent["removed"], dirty = True, True
                    state[p] = ent
            continue
        try:
            data = open(f, "rb").read()
            h, fid = sha(data), sha(p.encode())[:16]
            if ent.get("sha256") == h and not ent.get("removed") and os.path.isfile(os.path.join(out_dir, fid + ".age")):
                counts["unchanged"] += 1
                continue
            tmp = os.path.join(out_dir, fid + ".age.tmp")
            age(rcp + ["-o", tmp, f])
            os.replace(tmp, os.path.join(out_dir, fid + ".age"))
            state[p] = {"id": fid, "sha256": h, "size": len(data)}
            counts["encrypted"] += 1
            dirty = True
        except Exception as e:  # one file must never stop the others
            failed.append((p, str(e)[:160]))
    mpath = os.path.join(out_dir, "manifest.json.age")
    if dirty or not os.path.isfile(mpath):
        body = json.dumps({"version": 1, "items": state}, indent=1, sort_keys=True).encode()
        try:
            tmp = mpath + ".tmp"
            age(rcp + ["-o", tmp], data=body)
            os.replace(tmp, mpath)
        except Exception as e:
            failed.append(("manifest.json.age", str(e)[:160]))
    save_state(state)
    if (do_commit or do_push) and (counts["encrypted"] or dirty):
        g = ["git", "-C", dest]
        subprocess.run(g + ["add", "sealed/secrets"], check=True, capture_output=True)
        subprocess.run(g + ["commit", "-q", "-m", f"secrets: {counts['encrypted']} file(s) re-encrypted"], capture_output=True)
        if do_push:
            subprocess.run(g + ["push", "-q"], check=True, capture_output=True)
    return counts, failed, removed


def status():
    state, rows = load_state(), []
    for p in manifest_paths():
        f, ent = absolute(p), load_state().get(p)
        if not os.path.isfile(f):
            rows.append(("removed" if ent else "missing", p))
        elif not ent:
            rows.append(("new", p))
        else:
            rows.append(("ok" if ent["sha256"] == sha(open(f, "rb").read()) else "changed", p))
    return rows


def restore(identity, dest, force):
    out_dir = sealed_dir(dest)
    ident = ["-d", "-i", identity]
    items = json.loads(age(ident + [os.path.join(out_dir, "manifest.json.age")]))["items"]
    failed = 0
    for p, ent in sorted(items.items()):
        f = absolute(p)
        if os.path.isfile(f) and not force:
            print(f"{'exists, skipped':<16} {p}"); continue
        try:
            data = age(ident + [os.path.join(out_dir, ent["id"] + ".age")])
            if sha(data) != ent["sha256"]:
                raise RuntimeError("hash mismatch, file NOT written")
            os.makedirs(os.path.dirname(f), exist_ok=True)
            tmp = f + ".restore-tmp"
            open(tmp, "wb").write(data)
            os.replace(tmp, f)
            try:
                os.chmod(f, 0o600)
            except OSError:
                pass
            print(f"{'restored':<16} {p}")
        except Exception as e:
            failed += 1
            print(f"{'FAILED':<16} {p} ({str(e)[:100]})")
    return 1 if failed else 0


def main(argv):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["scan", "status", "backup", "run", "restore"])
    ap.add_argument("--add", action="store_true")
    ap.add_argument("--commit", action="store_true")
    ap.add_argument("--push", action="store_true")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--full-scan", action="store_true", help="run: walk ~/Codes even if the last scan is recent")
    ap.add_argument("--identity", default=os.environ.get("AGE_IDENTITY"))
    ap.add_argument("--identity-from-bw", metavar="NOTE", nargs="?", const=os.environ.get("AGE_IDENTITY_BW", "age-identity"),
                    help="restore: read the private key from this Bitwarden note (default age-identity)")
    a = ap.parse_args(argv)
    dest = default_dest()

    if a.cmd == "status":
        for st, p in status():
            print(f"{st:<10} {p}")
        return 0
    if a.cmd in ("backup", "run", "restore") and not dest:
        print("no destination: set SECRETS_DEST or keep an active id layer in <root>/self/manifest.json")
        return 2
    if a.cmd == "restore":
        if not (a.identity or a.identity_from_bw):
            print("restore needs --identity <file>, AGE_IDENTITY, or --identity-from-bw [NOTE] (Bitwarden)")
            return 2
        ident = a.identity if a.identity and not a.identity_from_bw else identity_from_bw(a.identity_from_bw)
        try:
            return restore(ident, dest, a.force)
        finally:
            if a.identity_from_bw:
                shutil.rmtree(os.path.dirname(ident), ignore_errors=True)

    stamp = os.path.join(STATE_DIR, "secrets-last-scan")
    recent = (a.cmd == "run" and not a.full_scan and os.path.isfile(stamp)
              and time.time() - os.path.getmtime(stamp) < SCAN_HOURS * 3600)
    found, skipped = ([], []) if recent else scan(dest)
    if a.cmd == "run" and not recent:
        os.makedirs(STATE_DIR, exist_ok=True)
        open(stamp, "w").write(str(time.time()))
    known = set(manifest_paths())
    new = [p for p in found if p not in known]
    if a.cmd == "scan":
        for p in found:
            print(f"{'known' if p in known else 'NEW':<10} {p}")
        for p, why in skipped:
            print(f"{'skipped':<10} {p} ({why})")
        if a.add and new:
            add_to_manifest(new)
            print(f"added {len(new)} path(s) to the manifest")
        return 0

    if a.cmd == "run" and new:
        add_to_manifest(new)
        inbox(f"New secrets in the automatic backup ({len(new)})",
              "Paths added to secrets-manifest.txt and encrypted with the age public key:\n" + "\n".join(new),
              ["Keep all", "Remove some from the manifest (say which)"])
    counts, failed, removed = backup(dest, a.commit, a.push)
    for p in new:
        print(f"{'added':<10} {p}")
    for p in removed:
        print(f"{'removed':<10} {p} (kept in backup)")
    for p, why in failed:
        print(f"{'FAILED':<10} {p} ({why})")
    print(f"summary: {counts['encrypted']} encrypted, {counts['unchanged']} unchanged, {len(new)} new, "
          f"{len(removed)} removed, {len(failed)} failed")
    if a.cmd == "run":
        if failed:
            inbox(f"Secrets backup failed ({len(failed)} file(s))",
                  "\n".join(f"{p}: {why}" for p, why in failed), ["Investigate now", "Ignore for now"])
        if removed:
            inbox(f"Secrets disappeared from the machine ({len(removed)})",
                  "They remain in the encrypted backup, nothing was deleted:\n" + "\n".join(removed),
                  ["Keep in the backup", "Remove from the manifest"])
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
