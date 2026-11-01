"""Offline tests for tools/secrets_backup.py with a fake `age` (dummy data only). Run: python -I -m unittest discover -s tests"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

TOOL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools", "secrets_backup.py")

FAKE_AGE = r'''
import base64, os, sys
a = sys.argv[1:]
log = os.environ.get("FAKE_AGE_LOG")
if log: open(log, "a").write(" ".join(a[:1]) + "\n")
dec = "-d" in a
rcp, ident, out, inp, i = [], None, None, None, 0
while i < len(a):
    if a[i] == "-r": rcp.append(a[i + 1]); i += 2
    elif a[i] == "-i": ident = a[i + 1]; i += 2
    elif a[i] == "-o": out = a[i + 1]; i += 2
    elif a[i] == "-d": i += 1
    else: inp = a[i]; i += 1
data = open(inp, "rb").read() if inp else sys.stdin.buffer.read()
if os.environ.get("FAKE_AGE_FAIL") and not dec and b"BOOM" in data: print("age: boom", file=sys.stderr); sys.exit(1)
if not dec:
    res = b"FAKEAGE\n" + ",".join(rcp).encode() + b"\n" + base64.b64encode(data)
else:
    head, who, body = data.split(b"\n", 2)
    secret = [l for l in open(ident).read().split() if l.startswith("AGE-SECRET-KEY-")][0]
    if "age1" + secret.replace("AGE-SECRET-KEY-", "") not in who.decode().split(","):
        print("age: no identity matched any of the recipients", file=sys.stderr); sys.exit(1)
    res = base64.b64decode(body)
if out: open(out, "wb").write(res)
else: sys.stdout.buffer.write(res)
'''

FAKE_DECISIONS = r'''
import json, os, sys
S = os.environ["FAKE_DEC_STATE"]
items = json.load(open(S)) if os.path.exists(S) else []
if sys.argv[1] == "list":
    for t in items: print("D-1   [open] manual: " + t)
elif sys.argv[1] == "add":
    items.append(sys.argv[2]); json.dump(items, open(S, "w"))
'''

SECRET = b"TOKEN=dummy-value-do-not-print"


def py(p):
    return f"{sys.executable.replace(chr(92), '/')} {p.replace(chr(92), '/')}"


class SecretsBackupTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.home = os.path.join(self.tmp, "home")
        self.dest = os.path.join(self.tmp, "dest")
        os.makedirs(self.dest)
        with open(os.path.join(self.dest, "layer.json"), "w") as fh:
            json.dump({"level": "id"}, fh)
        self.write("fake_age.py", FAKE_AGE, base=self.tmp)
        self.write("fake_dec.py", FAKE_DECISIONS, base=self.tmp)
        self.key = os.path.join(self.tmp, "id.txt")
        open(self.key, "w").write("AGE-SECRET-KEY-TEST1\n")
        self.env = dict(os.environ, SECRETS_HOME=self.home, SECRETS_DEST=self.dest, AGE_RECIPIENT="age1TEST1",
                        AGE_CMD=py(os.path.join(self.tmp, "fake_age.py")), FAKE_AGE_LOG=os.path.join(self.tmp, "age.log"),
                        SECRETS_DECISIONS_CMD=py(os.path.join(self.tmp, "fake_dec.py")),
                        FAKE_DEC_STATE=os.path.join(self.tmp, "dec.json"))
        self.env["SECRETS_SCAN_HOURS"] = "0"
        for k in ("AGE_IDENTITY", "SECRETS_INCLUDE_CODEX_AUTH", "FAKE_AGE_FAIL"):
            self.env.pop(k, None)
        for p, data in {
            "Codes/app/.env": SECRET, "Codes/app/.env.local": b"A=1", "Codes/app/.env.example": b"A=",
            "Codes/app/cert.pem": b"pem-dummy", "Codes/app/id_utils.py": b"x=1", "Codes/app/creds.py": b"x=1",
            "Codes/app/node_modules/pkg/.env": b"skip", "Codes/app/venv-abc/x.pem": b"skip",
            "Codes/app/credentials.json": b"{}", ".ssh/id_ed25519": b"key-dummy", ".ssh/id_ed25519.pub": b"pub",
            ".omni/pgpw.txt": b"pw-dummy", ".codex/auth.json": b"codex-dummy",
        }.items():
            self.write(p, data, base=self.home)
        self.write(".claude/scripts/secrets-scan-dirs.txt", "~/.omni\n", base=self.home)  # id-layer list of extra dirs
        subprocess.run(["git", "init", "-q", os.path.join(self.home, "Codes", "tracked")], check=True)
        self.write("Codes/tracked/fixtures/test.pem", b"public-fixture", base=self.home)
        subprocess.run(["git", "-C", os.path.join(self.home, "Codes", "tracked"), "add", "-A"], check=True)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def write(self, rel, data, base):
        path = os.path.join(base, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb" if isinstance(data, bytes) else "w") as fh:
            fh.write(data)

    def run_tool(self, *args, **extra):
        env = dict(self.env, **extra)
        p = subprocess.run([sys.executable, "-I", TOOL, *args], env=env, capture_output=True, encoding="utf-8")
        self.out = (p.stdout or "") + (p.stderr or "")
        return p.returncode

    def sealed(self):
        return os.path.join(self.dest, "sealed", "secrets")

    def age_calls(self):
        log = self.env["FAKE_AGE_LOG"]
        return len(open(log).read().split()) if os.path.exists(log) else 0

    def test_scan_matches_patterns_and_skips_noise(self):
        self.assertEqual(self.run_tool("scan"), 0)
        found = {l.split()[1] for l in self.out.splitlines() if l.startswith("NEW")}
        self.assertEqual(found, {"~/Codes/app/.env", "~/Codes/app/.env.local", "~/Codes/app/cert.pem",
                                 "~/Codes/app/credentials.json", "~/.ssh/id_ed25519", "~/.omni/pgpw.txt"})
        self.assertIn("tracked by git", self.out)
        self.assertNotIn("auth.json", self.out)

    def test_extra_scan_dirs_come_from_the_id_file(self):
        self.write(".extra/token.pem", b"x", base=self.home)
        self.run_tool("scan")
        self.assertNotIn(".extra", self.out)
        self.write(".claude/scripts/secrets-scan-dirs.txt", "\n".join(["# more", "~/.extra", ""]), base=self.home)
        self.run_tool("scan")
        self.assertIn("NEW        ~/.extra/token.pem", self.out)

    def test_codex_auth_only_when_asked(self):
        self.run_tool("scan", SECRETS_INCLUDE_CODEX_AUTH="1")
        self.assertIn("~/.codex/auth.json", self.out)

    def test_run_encrypts_and_never_leaks(self):
        self.assertEqual(self.run_tool("run"), 0)
        self.assertIn("6 encrypted", self.out)
        names = sorted(os.listdir(self.sealed()))
        self.assertEqual(len(names), 7)
        self.assertIn("manifest.json.age", names)
        self.assertTrue(all(n.endswith(".age") for n in names))
        for n in names:  # ciphertext and file names never carry plaintext or the original paths
            blob = open(os.path.join(self.sealed(), n), "rb").read()
            self.assertNotIn(SECRET, blob)
            self.assertNotIn(b".env", n.encode())
        state = open(os.path.join(self.home, ".claude", "state", "secrets-hashes.json")).read()
        self.assertNotIn(SECRET.decode(), state)
        self.assertNotIn("dummy-value", self.out)
        manifest = open(os.path.join(self.home, ".claude", "scripts", "secrets-manifest.txt")).read()
        self.assertIn("~/Codes/app/.env", manifest)
        self.assertEqual(json.load(open(self.env["FAKE_DEC_STATE"])), ["Segredos novos no backup automático (6)"])

    def test_only_changed_files_are_reencrypted(self):
        self.run_tool("run")
        before = self.age_calls()
        self.assertEqual(self.run_tool("run"), 0)
        self.assertEqual(self.age_calls(), before)  # nothing changed: age not called at all
        self.assertEqual(len(json.load(open(self.env["FAKE_DEC_STATE"]))), 1)  # inbox deduped
        self.write("Codes/app/.env", b"TOKEN=changed", base=self.home)
        self.run_tool("run")
        self.assertEqual(self.age_calls() - before, 2)  # the file + the manifest
        self.assertIn("1 encrypted, 5 unchanged", self.out)

    def test_scan_cooldown_and_noise_filters(self):
        self.write("Codes/app/.deps/certifi/cacert.pem", b"public", base=self.home)
        self.write("Codes/app/.claude/worktrees/x/.env", b"copy", base=self.home)
        self.run_tool("run", SECRETS_SCAN_HOURS="6")
        self.assertNotIn("cacert", self.out + open(os.path.join(self.home, ".claude", "scripts", "secrets-manifest.txt")).read())
        self.write("Codes/app/new.pem", b"later", base=self.home)
        self.run_tool("run", SECRETS_SCAN_HOURS="6")  # inside the cooldown: the walk is skipped
        self.assertNotIn("new.pem", self.out)
        self.run_tool("run", SECRETS_SCAN_HOURS="6", **{})  # still skipped
        self.assertEqual(self.run_tool("run", "--full-scan", SECRETS_SCAN_HOURS="6"), 0)
        self.assertIn("added      ~/Codes/app/new.pem", self.out)

    def test_removed_file_is_flagged_and_kept(self):
        self.run_tool("run")
        os.remove(os.path.join(self.home, "Codes", "app", "cert.pem"))
        self.run_tool("run")
        self.assertIn("removed    ~/Codes/app/cert.pem (kept in backup)", self.out)
        self.assertEqual(len(os.listdir(self.sealed())), 7)  # nothing deleted from the backup
        manifest = open(os.path.join(self.home, ".claude", "scripts", "secrets-manifest.txt")).read()
        self.assertIn("~/Codes/app/cert.pem", manifest)  # nor from the manifest
        self.assertTrue(any("sumiram" in t for t in json.load(open(self.env["FAKE_DEC_STATE"]))))

    def test_failure_does_not_stop_others_and_goes_to_inbox(self):
        self.write("Codes/app/.env.boom", b"BOOM", base=self.home)
        self.assertEqual(self.run_tool("run", FAKE_AGE_FAIL="1"), 1)
        self.assertIn("FAILED", self.out)
        self.assertIn("6 encrypted", self.out)
        self.assertTrue(any("falhou" in t for t in json.load(open(self.env["FAKE_DEC_STATE"]))))

    def test_restore_roundtrip_skips_existing_and_rejects_wrong_key(self):
        self.run_tool("run")
        os.remove(os.path.join(self.home, "Codes", "app", ".env"))
        self.assertEqual(self.run_tool("restore", "--identity", self.key), 0)
        self.assertEqual(open(os.path.join(self.home, "Codes", "app", ".env"), "rb").read(), SECRET)
        self.assertIn("exists, skipped", self.out)
        self.assertNotIn("dummy-value", self.out)
        other = os.path.join(self.tmp, "other.txt")
        open(other, "w").write("AGE-SECRET-KEY-OTHER\n")
        self.assertNotEqual(self.run_tool("restore", "--identity", other), 0)

    def test_dest_must_be_the_id_layer_and_not_superego(self):
        repo = os.path.dirname(os.path.dirname(os.path.abspath(TOOL)))
        self.assertNotEqual(self.run_tool("run", SECRETS_DEST=repo), 0)
        self.assertIn("must not be the superego repo", self.out)
        self.assertFalse(os.path.exists(os.path.join(repo, "sealed")))
        ego = os.path.join(self.tmp, "ego")
        self.write("layer.json", json.dumps({"level": "ego"}), base=ego)
        self.assertNotEqual(self.run_tool("run", SECRETS_DEST=ego), 0)
        self.assertIn("must be the id layer repo", self.out)
        self.assertFalse(os.path.exists(os.path.join(ego, "sealed")))

    def test_destination_defaults_to_the_id_layer_of_the_manifest(self):
        env = dict(self.env)
        env.pop("SECRETS_DEST")
        man = os.path.join(self.tmp, "manifest.json")
        with open(man, "w") as fh:
            json.dump({"layers": [{"level": "ego", "path": "x"}, {"level": "id", "path": self.dest, "active": True}]}, fh)
        env["SYNC_MANIFEST"] = man
        p = subprocess.run([sys.executable, "-I", TOOL, "run"], env=env, capture_output=True, encoding="utf-8")
        self.assertEqual(p.returncode, 0, p.stdout + p.stderr)
        self.assertTrue(os.path.isfile(os.path.join(self.sealed(), "manifest.json.age")))
        env["SYNC_MANIFEST"] = os.path.join(self.tmp, "missing.json")  # no id layer, no SECRETS_DEST: clear refusal
        p = subprocess.run([sys.executable, "-I", TOOL, "run"], env=env, capture_output=True, encoding="utf-8")
        self.assertEqual(p.returncode, 2)

    def test_public_key_comes_from_the_shared_id_context_file(self):
        self.env.pop("AGE_RECIPIENT")
        self.assertNotEqual(self.run_tool("run"), 0)  # no key anywhere: refuses
        self.write(".config/id-context/recipient", "\n".join(["# note", "age1TEST1", ""]), base=self.home)
        self.assertEqual(self.run_tool("run"), 0)
        self.assertIn("6 encrypted", self.out)

    def test_restore_reads_the_private_key_from_a_bitwarden_note(self):
        fake_bw = os.path.join(self.tmp, "fake_bw.py")
        with open(fake_bw, "w") as fh:
            fh.write("\n".join(["import sys",
                                "if sys.argv[1:3] == ['get', 'notes'] and sys.argv[3] == 'age-identity':",
                                "    print('# created: dummy')",
                                "    print('AGE-SECRET-KEY-TEST1')",
                                "else:",
                                "    sys.exit(1)", ""]))
        self.run_tool("run")
        os.remove(os.path.join(self.home, "Codes", "app", ".env"))
        env = {"VAULT_BW_CMD": py(fake_bw), "BW_SESSION": "x"}
        self.assertEqual(self.run_tool("restore", "--identity-from-bw", **env), 0)
        self.assertEqual(open(os.path.join(self.home, "Codes", "app", ".env"), "rb").read(), SECRET)
        self.assertNotIn("AGE-SECRET-KEY", self.out)
        self.assertNotEqual(self.run_tool("restore", "--identity-from-bw", "nope", **env), 0)  # missing note
        self.assertNotEqual(self.run_tool("restore", "--identity-from-bw", VAULT_BW_CMD=py(fake_bw), BW_SESSION=""), 0)

    @unittest.skipUnless(shutil.which("age") and shutil.which("age-keygen"), "real age not installed")
    def test_real_age_roundtrip(self):
        key = os.path.join(self.tmp, "real.txt")
        pub = subprocess.run(["age-keygen", "-o", key], capture_output=True, encoding="utf-8").stderr.split()[-1]
        env = {"AGE_CMD": "age", "AGE_RECIPIENT": pub}
        self.env.update(env)
        self.assertEqual(self.run_tool("run"), 0)
        os.remove(os.path.join(self.home, "Codes", "app", ".env"))
        self.assertEqual(self.run_tool("restore", "--identity", key), 0)
        self.assertEqual(open(os.path.join(self.home, "Codes", "app", ".env"), "rb").read(), SECRET)


if __name__ == "__main__":
    unittest.main()
