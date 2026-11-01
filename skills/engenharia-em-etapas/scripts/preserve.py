"""Check that a rewrite kept every fact token of the original.

Usage: python preserve.py ORIGINAL.md REVISED.md
Compares, as multisets: headings, fenced code blocks, inline code, [tags], link URLs, IDs and numbers.
Prints LOST (in original, missing or fewer in revised) and ADDED (new in revised). Exit 1 if anything is
LOST in headings, code, tags, URLs or IDs, or if a number was ADDED.
"""
import re
import sys
from collections import Counter

ID = r"(?<![\w-])(?:ADR-\d{1,2}(?!\d)|BR\d+|QS\d+|AC\d+|[RPGNAQLICKDUT]\d+[a-z]?)(?![\w])"


def tokens(text):
    fences = re.findall(r"```.*?```", text, flags=re.S)
    prose = re.sub(r"```.*?```", "", text, flags=re.S)
    out = {
        "heading": Counter(l.strip() for l in prose.splitlines() if re.match(r"^#{1,6} ", l)),
        "code": Counter(fences),
        "inline": Counter(re.findall(r"`[^`\n]+`", prose)),
        "tag": Counter(re.findall(r"\[(?:LIVE|FILES|PLATFORM|NOT VERIFIED|RENDER|\?)[^\]]*\]", prose)),
        "url": Counter(re.findall(r"\]\(([^)\s]+)\)", prose)),
    }
    bare = re.sub(r"`[^`\n]+`", "", prose)
    bare = re.sub(r"\]\([^)]*\)", "]", bare)
    out["id"] = Counter(re.findall(ID, bare))
    out["number"] = Counter(re.findall(r"(?<![\w.])\d[\d.,:]*\d%?|(?<![\w.])\d%?", bare))
    return out


def _usage():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print("Usage: python preserve.py ORIGINAL.md REVISED.md")
        print(__doc__)
        sys.exit(0)


def main():
    _usage()
    a = tokens(open(sys.argv[1], encoding="utf-8").read())
    b = tokens(open(sys.argv[2], encoding="utf-8").read())
    bad = False
    for kind in a:
        lost = a[kind] - b[kind]
        added = b[kind] - a[kind]
        strict_lost = kind in ("heading", "code", "tag", "url", "id")
        if lost:
            print(f"LOST {kind} ({sum(lost.values())}):", list(lost.items())[:40])
            bad = bad or strict_lost
        if added and kind in ("number", "id", "tag", "url", "code"):
            print(f"ADDED {kind} ({sum(added.values())}):", list(added.items())[:40])
            bad = bad or kind == "number"
    print("RESULT:", "FAIL" if bad else "OK")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
