"""Vault step of the person install: the person's OWN Bitwarden vault holds their OWN age identity.

Nothing here touches anyone else's vault. Secrets never go on a command line or into the output: the age identity
is read from the stdout of `age-keygen`, sent to `bw` through stdin as a Python-built payload, verified by hash
comparison, and kept on disk nowhere (only the PUBLIC recipient is saved, in ~/.config/id-context/recipient).
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
from pathlib import Path

NOTE = "age-identity"
KEY_MARK = "AGE-SECRET-KEY-"
SERVERS = {"us": "https://vault.bitwarden.com", "eu": "https://vault.bitwarden.eu"}
HUMAN_STEPS = """Create your Bitwarden account (only you can do these steps):
  1. Open https://vault.bitwarden.{tld} and choose 'Create account'.
  2. Set a long master password that you do NOT use anywhere else. Write it down away from the computer: without it
     and the recovery code there is no way to open the vault.
  3. Turn on two-step verification (Settings > Security) and SAVE the recovery code.
  4. Come back here. The installer will ask for the bw login and the master password (only in your terminal)."""


def sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def b64json(obj: dict) -> str:
    return base64.b64encode(json.dumps(obj).encode("utf-8")).decode()


def has_key(text: str) -> bool:
    return KEY_MARK in text


def recipient_of(identity_text: str) -> str:
    m = re.search(r"#\s*public key:\s*(age1[0-9a-z]+)", identity_text)
    return m.group(1) if m else ""


class Vault:
    """bw and age through an injected shell wrapper (tools/onboard.py Sh): input goes to stdin, never to argv."""

    def __init__(self, sh, say):
        self.sh, self.say = sh, say

    def status(self) -> str:
        res = self.sh.run(["bw", "status"], check=False)
        try:
            return json.loads(res.stdout or "{}").get("status", "unauthenticated")
        except ValueError:
            return "unauthenticated"

    def set_region(self, region: str) -> None:
        if region not in SERVERS:
            raise ValueError("region must be us or eu")
        if self.status() == "unauthenticated":  # bw only accepts a server change while logged out
            self.sh.run(["bw", "config", "server", SERVERS[region]], check=False)

    def unlock(self, interactive: bool) -> bool:
        """Leave BW_SESSION in this process's environment only. False when it cannot be done here."""
        if self.sh.env.get("BW_SESSION"):
            return True
        st = self.status()
        if not interactive:
            return False
        if st == "unauthenticated":
            if self.sh.run(["bw", "login"], check=False, interactive=True).returncode != 0:
                return False
        res = self.sh.run(["bw", "unlock", "--raw"], check=False, interactive=True, capture_stdout=True)
        token = (res.stdout or "").strip()
        if res.returncode != 0 or not token:
            return False
        self.sh.env["BW_SESSION"] = token
        return True

    def read_note(self, name: str = NOTE) -> str:
        res = self.sh.run(["bw", "get", "notes", name], check=False)
        return res.stdout if res.returncode == 0 else ""

    def store_note(self, text: str, name: str = NOTE) -> None:
        item = {"type": 2, "name": name, "notes": text, "secureNote": {"type": 0}, "fields": []}
        self.sh.run(["bw", "create", "item"], input=b64json(item))
        self.sh.run(["bw", "sync"], check=False)

    def generate(self) -> tuple[str, str]:
        """(identity text, recipient). The identity only ever lives in this process."""
        res = self.sh.run(["age-keygen"])
        text = res.stdout or ""
        rcp = recipient_of(text) or recipient_of(res.stderr or "") or re.sub(r"^.*?(age1[0-9a-z]+).*$", r"\1", res.stderr or "").strip()
        if not has_key(text) or not rcp.startswith("age1"):
            raise RuntimeError("age-keygen did not produce an identity")
        return text, rcp

    def recipient_for(self, identity_text: str) -> str:
        res = self.sh.run(["age-keygen", "-y"], input=identity_text)
        return (res.stdout or "").strip()

    def ensure_identity(self) -> tuple[str, str]:
        """(status, recipient): reuse the vault note when it holds a key, else create it and verify it by hash."""
        have = self.read_note()
        if has_key(have):
            return "reused from the vault", self.recipient_for(have)
        text, rcp = self.generate()
        self.store_note(text)
        if sha(self.read_note()) != sha(text) and sha(self.read_note().strip()) != sha(text.strip()):
            raise RuntimeError("the note in the vault does not match the generated key; nothing was deleted")
        return "created and verified in the vault", rcp


def save_recipient(home: Path, recipient: str) -> Path:
    p = home / ".config" / "id-context" / "recipient"  # legacy folder name, kept so existing recipients keep working
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(recipient + "\n", encoding="utf-8", newline="\n")
    return p
