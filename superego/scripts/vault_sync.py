#!/usr/bin/env python3
"""Sync the files in secrets-manifest.txt with Bitwarden secure notes (free account: no attachments).

  vault_sync.py status           disk vs vault by sha256 of the exact bytes
  vault_sync.py push             disk -> vault, only files whose hash changed
  (any mode accepts --manifest FILE to use another path list)
  vault_sync.py pull [--force]   vault -> disk, verified by sha256, skips existing files unless --force

Storage per file "claude-context/<path>": a head item with fields sha256/enc/tail/parts and chunk 1 in notes;
chunks 2..N live in items "claude-context/<path>#k". Small clean text is stored plain (readable in the app),
anything else (CRLF, binary, big) as base64(gzip). Chunks are 5000 chars: the vault limit is 10000 ENCRYPTED chars.
One failing file never stops the others; exit code is 1 if any failed. Secret values are never printed.
Env: BW_SESSION (or ~/.bw-session), VAULT_BW_CMD, VAULT_HOME, VAULT_MANIFEST (the last three are for tests).
"""
import base64, gzip, hashlib, json, os, shlex, shutil, subprocess, sys

CHUNK = 5000
PREFIX = "claude-context/"
HOME = os.environ.get("VAULT_HOME") or os.path.expanduser("~")
BW = shlex.split(os.environ.get("VAULT_BW_CMD", "bw"))
BW[0] = shutil.which(BW[0]) or BW[0]


class BwError(Exception):
    pass


def bw(*args, data=None):
    p = subprocess.run(BW + list(args), input=data, capture_output=True, encoding="utf-8", env=os.environ)
    if p.returncode != 0:
        raise BwError(f"bw {' '.join(args[:2])} failed: {p.stderr.strip()[:160]}")
    return p.stdout


def b64json(obj):
    return base64.b64encode(json.dumps(obj).encode("utf-8")).decode()


def encode(data):
    """-> (enc, tail, chunks). Plain only when it round-trips safely; the tail (trailing whitespace) is kept apart."""
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        text = None
    if text is not None and "\r" not in text and "\x00" not in text:
        body = text.rstrip()
        if body and body == body.lstrip() and len(body.encode("utf-8")) <= CHUNK:
            return "plain", text[len(body):], [body]
    raw = base64.b64encode(gzip.compress(data, mtime=0)).decode()
    return "b64gz", "", [raw[i:i + CHUNK] for i in range(0, len(raw), CHUNK)] or [""]


def decode(enc, tail, chunks):
    joined = "".join(chunks)
    if enc == "plain":
        return (joined + tail).encode("utf-8")
    return gzip.decompress(base64.b64decode(joined))


def field(item, name):
    for f in item.get("fields") or []:
        if f.get("name") == name:
            return f.get("value")
    return None


def list_parts(name):
    items = json.loads(bw("list", "items", "--search", name) or "[]")
    return {i["name"]: i for i in items if i["name"] == name or i["name"].startswith(name + "#")}


def part_name(name, k):
    return name if k == 1 else f"{name}#{k}"


def upsert(nm, notes, fields, existing):
    if existing:
        item = json.loads(bw("get", "item", existing["id"]))
        item["notes"], item["fields"] = notes, fields
        bw("edit", "item", existing["id"], data=b64json(item))
    else:
        bw("create", "item", data=b64json(
            {"type": 2, "name": nm, "notes": notes, "secureNote": {"type": 0}, "fields": fields}))


def sha(data):
    return hashlib.sha256(data).hexdigest()


def status_one(p, f, name):
    head = list_parts(name).get(name)
    if os.path.isfile(f) and head:
        same = field(head, "sha256") == sha(open(f, "rb").read())
        return "ok" if same else "changed"
    return "only-disk" if os.path.isfile(f) else ("only-vault" if head else "missing")


def push_one(p, f, name):
    if not os.path.isfile(f):
        return "skip (missing)"
    data = open(f, "rb").read()
    h = sha(data)
    parts = list_parts(name)
    head = parts.get(name)
    if head and field(head, "sha256") == h and len(parts) == int(field(head, "parts") or 0):
        return "unchanged"
    enc, tail, chunks = encode(data)
    fields = [{"name": "sha256", "value": h, "type": 0}, {"name": "enc", "value": enc, "type": 0},
              {"name": "tail", "value": json.dumps(tail), "type": 0},
              {"name": "parts", "value": str(len(chunks)), "type": 0}]
    for k, chunk in enumerate(chunks, 1):
        nm = part_name(name, k)
        upsert(nm, chunk, fields if k == 1 else [], parts.get(nm))
    keep = {part_name(name, k) for k in range(1, len(chunks) + 1)}
    for nm, item in parts.items():
        if nm not in keep:
            bw("delete", "item", item["id"])
    return "updated" if head else "created"


def pull_one(p, f, name, force):
    if os.path.isfile(f) and not force:
        return "exists, skipped"
    parts = list_parts(name)
    head = parts.get(name)
    if not head:
        return "not in vault"
    want = field(head, "sha256")
    if not want:
        raise BwError("legacy item without sha256: run push first")
    n = int(field(head, "parts") or 1)
    chunks = []
    for k in range(1, n + 1):
        item = parts.get(part_name(name, k))
        if not item:
            raise BwError(f"part {k}/{n} missing in vault")
        full = json.loads(bw("get", "item", item["id"]))
        chunks.append(full.get("notes") or "")
    data = decode(field(head, "enc"), json.loads(field(head, "tail") or '""'), chunks)
    if sha(data) != want:
        raise BwError("hash mismatch after reassembly, file NOT written")
    os.makedirs(os.path.dirname(f), exist_ok=True)
    tmp = f + ".vault-tmp"
    with open(tmp, "wb") as fh:
        fh.write(data)
    os.replace(tmp, f)
    try:
        os.chmod(f, 0o600)
    except OSError:
        pass
    return "restored"


def main(argv):
    if not argv or argv[0] not in ("status", "push", "pull"):
        print("usage: vault_sync.py status|push|pull [--force]")
        return 2
    mode, force = argv[0], "--force" in argv[1:]
    if "--manifest" in argv:  # e.g. the age identity manifest used by restore-machine
        os.environ["VAULT_MANIFEST"] = argv[argv.index("--manifest") + 1]
    if not os.environ.get("BW_SESSION"):
        sess = os.path.join(HOME, ".bw-session")
        if os.path.isfile(sess):
            os.environ["BW_SESSION"] = open(sess).read().strip()
    if not os.environ.get("BW_SESSION"):
        print('locked: run  export BW_SESSION="$(bw unlock --raw)"')
        return 2
    manifest = os.environ.get("VAULT_MANIFEST") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "secrets-manifest.txt")
    paths = [l.strip() for l in open(manifest, encoding="utf-8") if l.strip() and not l.lstrip().startswith("#")]
    try:
        bw("sync")
    except BwError as e:
        print(f"FAILED sync: {e}")
        return 1
    counts, failed = {}, 0
    for p in paths:
        f = HOME + p[1:] if p.startswith("~") else p
        name = PREFIX + p
        try:
            res = {"status": lambda: status_one(p, f, name), "push": lambda: push_one(p, f, name),
                   "pull": lambda: pull_one(p, f, name, force)}[mode]()
        except Exception as e:  # one file must never stop the others
            res, failed = f"FAILED ({e})", failed + 1
        counts[res.split(" (")[0]] = counts.get(res.split(" (")[0], 0) + 1
        print(f"{res:<18} {p}")
    print("summary: " + ", ".join(f"{v} {k}" for k, v in sorted(counts.items())))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
