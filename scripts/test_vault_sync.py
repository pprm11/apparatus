#!/usr/bin/env python3
"""Offline test of vault_sync.py with a fake `bw` (no network, dummy data only). Run: python -I test_vault_sync.py"""
import json, os, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__)).replace("\\", "/")
SHIM = '''
import base64, json, os, sys
S = os.environ["FAKE_BW_STATE"]
st = json.load(open(S)) if os.path.exists(S) else {"seq": 0, "items": {}}
a = sys.argv[1:]
def save(): json.dump(st, open(S, "w"))
def norm(it):  # what the real vault is suspected to do: CRLF -> LF, trailing whitespace stripped
    it["notes"] = (it.get("notes") or "").replace("\\r\\n", "\\n").rstrip()
    if len(it["notes"]) > 6900: print("400 Notes exceeds the maximum encrypted value length of 10000", file=sys.stderr); sys.exit(1)
    if "FAILME" in it["name"]: print("500 boom", file=sys.stderr); sys.exit(1)
if a[0] == "sync": pass
elif a[:2] == ["list", "items"]:
    print(json.dumps([i for i in st["items"].values() if a[3] in i["name"]]))
elif a[:2] == ["get", "item"]: print(json.dumps(st["items"][a[2]]))
elif a[:2] in (["create", "item"], ["edit", "item"]):
    it = json.loads(base64.b64decode(sys.stdin.read()))
    norm(it)
    if a[0] == "create": st["seq"] += 1; it["id"] = "id%d" % st["seq"]
    else: it["id"] = a[2]
    st["items"][it["id"]] = it; save()
elif a[:2] == ["delete", "item"]: del st["items"][a[2]]; save()
'''


def main():
    tmp = tempfile.mkdtemp().replace("\\", "/")
    home = tmp + "/home"
    os.makedirs(home)
    shim = tmp + "/fake_bw.py"
    open(shim, "w").write(SHIM)
    files = {"small.env": b"KEY=dummy\n", "crlf.env": b"A=1\r\nB=2\r\n", "big.bin": os.urandom(20000),
             "FAILME.env": b"X=1\n", "last.env": b"Z=9", "lead.env": b"  indented=1\n\n\n"}
    for n, d in files.items():
        open(f"{home}/{n}", "wb").write(d)
    manifest = tmp + "/manifest.txt"
    open(manifest, "w").write("# test\n" + "".join(f"~/{n}\n" for n in files))
    env = dict(os.environ, VAULT_HOME=home, VAULT_MANIFEST=manifest, BW_SESSION="x", FAKE_BW_STATE=tmp + "/state.json",
               VAULT_BW_CMD=f"{sys.executable.replace(chr(92), '/')} {shim}")
    outputs = []

    def run(*a):
        p = subprocess.run([sys.executable, "-I", HERE + "/vault_sync.py", *a], env=env, capture_output=True, encoding="utf-8")
        outputs.append(p.stdout + p.stderr)
        return p.returncode, p.stdout

    def cnt(out, label):
        return sum(1 for l in out.splitlines() if l.startswith(label))

    def state():
        return json.load(open(env["FAKE_BW_STATE"]))["items"]

    rc, out = run("push")
    assert rc == 1 and "FAILED" in out and cnt(out, "created") == 5, out          # failure in the middle, rest done
    names = sorted(i["name"] for i in state().values())
    assert any(n.endswith("big.bin#4") for n in names), names                         # big file split in chunks
    rc, out = run("status")
    assert cnt(out, "ok") == 5, out                                                 # no false "changed"
    for n in files:
        if n != "FAILME.env":
            os.remove(f"{home}/{n}")
    rc, out = run("pull")
    assert cnt(out, "restored") == 5, out
    for n, d in files.items():
        if n != "FAILME.env":
            assert open(f"{home}/{n}", "rb").read() == d, n                           # byte-exact: CRLF, tail, binary
    rc, out = run("pull")
    assert cnt(out, "exists, skipped") == 6, out
    open(f"{home}/big.bin", "wb").write(b"tiny")                                      # shrink: surplus chunks deleted
    rc, out = run("push")
    assert "updated" in out and cnt(out, "unchanged") == 4, out
    assert not any("big.bin#" in i["name"] for i in state().values())
    open(f"{home}/crlf.env", "wb").write(b"A=1\r\nB=3\r\n")
    assert "changed" in run("status")[1]
    run("push")
    rc, out = run("push")
    assert cnt(out, "unchanged") == 5, out
    blob = "\n".join(outputs)
    assert "KEY=dummy" not in blob and "A=1" not in blob and "indented" not in blob   # no secret in output
    print("all vault_sync tests passed")


main()
