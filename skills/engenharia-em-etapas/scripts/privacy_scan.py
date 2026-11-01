"""Scan documents or a built page for data that must not be published.

Usage: python privacy_scan.py FILE ...
Reports, with file and line: Brazilian phone numbers (55 + DDD + 8 or 9 digits), CPF, e-mail addresses,
API tokens and keys, Slack links, database URLs with credentials. Exit 1 when anything is found.
Synthetic numbers start with 55629900 (13 digits) or 55629000 (the same number in the 12-digit form) and are skipped; any other test number is reported.
"""
import re
import sys

SYNTHETIC = ("55629900", "55629000")  # 13-digit synthetic and its 12-digit form without the leading 9
PATTERNS = {
    "phone": r"(?<!\d)55\d{10,11}(?!\d)",
    "cpf": r"(?<!\d)\d{3}\.\d{3}\.\d{3}-\d{2}(?!\d)",
    "email": r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[a-z]{2,}",
    "token": r"sk-[A-Za-z0-9]{16,}|ghp_[A-Za-z0-9]{20,}|github_pat_\w{20,}|AKIA[0-9A-Z]{16}|eyJ[\w-]{20,}\.[\w-]{10,}|xox[abp]-[\w-]{10,}",
    "slack": r"https://[a-z0-9-]+\.slack\.com/\S+",
    "db_url": r"(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis)://[^\s\"'<>]*:[^\s\"'<>@]+@",
}


def _usage():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print("Usage: python privacy_scan.py FILE ...")
        print(__doc__)
        sys.exit(0)


def main():
    _usage()
    found = 0
    for f in sys.argv[1:]:
        for n, line in enumerate(open(f, encoding="utf-8", errors="replace"), 1):
            for kind, pat in PATTERNS.items():
                for m in re.finditer(pat, line):
                    if kind == "phone" and m.group(0).startswith(SYNTHETIC):
                        continue
                    print(f"{f}:{n}: {kind}: {m.group(0)[:60]}")
                    found += 1
    print("RESULT:", "FOUND " + str(found) if found else "CLEAN")
    sys.exit(1 if found else 0)


if __name__ == "__main__":
    main()
