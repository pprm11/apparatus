"""Turn repository references in Markdown into permalinks that open the exact lines at one commit.

Usage:
  python permalinks.py --repo-dir <git checkout> --sha <commit> --github <owner/repo> [--check] FILE.md ...

A reference is inline code `path`, `path:lines` or `prefix:path:lines` (the as-is prefix, which is dropped) (lines: 70, 88-100 or 46,70) whose path exists in the
tree of <sha>. It becomes [`path:lines`](https://github.com/<owner/repo>/blob/<full sha>/path#L88-L100);
Markdown files get ?plain=1 so GitHub shows the source and jumps to the line. A list such as 46,70 becomes
one link per line. References inside fenced code or already inside a link are left alone. Paths that
look like repository paths but are not in the tree are reported, as are line numbers past the end of the
file, and cited lines that differ from the file in the checkout (a sign the text was read at another
commit than --sha). --check only reports. --show prints the cited lines (and writes nothing) so a reader can confirm each one.
"""
import argparse
import os
import re
import subprocess
import sys

REF = re.compile(r"(?<!\[)`(?:[a-z0-9]+:(?=[A-Za-z0-9_.\-]+/))?([A-Za-z0-9_.\-/]+\.[A-Za-z0-9]+)(?::([\d,\-]+))?`(?!\]\()")


def git(repo, *args):
    return subprocess.run(["git", "-C", repo, *args], capture_output=True, text=True, encoding="utf-8", check=True).stdout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo-dir", required=True)
    ap.add_argument("--sha", required=True)
    ap.add_argument("--github", required=True)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--show", action="store_true", help="print the cited lines of every reference, to confirm they say what the text claims")
    ap.add_argument("files", nargs="+")
    a = ap.parse_args()
    sha = git(a.repo_dir, "rev-parse", a.sha).strip()
    tree = set(git(a.repo_dir, "ls-tree", "-r", "--name-only", sha).splitlines())
    tops = {p.split("/")[0] for p in tree if "/" in p}
    sizes = {}
    problems = 0

    def length(path):
        if path not in sizes:
            sizes[path] = git(a.repo_dir, "show", f"{sha}:{path}").count("\n") + 1
        return sizes[path]

    def url(path, first, last=None):
        plain = "?plain=1" if path.endswith((".md", ".mdx")) else ""
        anchor = f"#L{first}" + (f"-L{last}" if last and last != first else "")
        return f"https://github.com/{a.github}/blob/{sha}/{path}{plain}{anchor}"

    for f in a.files:
        text = open(f, encoding="utf-8").read()
        parts = re.split(r"(```.*?```)", text, flags=re.S)
        changed = 0
        for i, part in enumerate(parts):
            if part.startswith("```"):
                continue

            def repl(m):
                nonlocal changed, problems
                path, lines = m.group(1), m.group(2)
                if path not in tree:
                    if path.split("/")[0] in tops:
                        print(f"{f}: NOT IN TREE at {sha[:7]}: {path}")
                        problems += 1
                    return m.group(0)
                n = length(path)
                if not lines:
                    changed += 1
                    return f"[`{path}`](https://github.com/{a.github}/blob/{sha}/{path})"
                links = []
                for k, chunk in enumerate(lines.split(",")):
                    lo, _, hi = chunk.partition("-")
                    if a.show:
                        body = git(a.repo_dir, "show", f"{sha}:{path}").splitlines()
                        print(f"--- {path}:{chunk}")
                        for ln in range(int(lo), min(int(hi or lo), n) + 1):
                            print(f"{ln:>5} {body[ln - 1][:160]}")
                    wt = os.path.join(a.repo_dir, path)
                    if os.path.exists(wt):
                        cited = git(a.repo_dir, "show", f"{sha}:{path}").splitlines()[int(lo) - 1:int(hi or lo)]
                        local = open(wt, encoding="utf-8", errors="replace").read().splitlines()[int(lo) - 1:int(hi or lo)]
                        if cited != local:
                            print(f"{f}: LINES DIFFER FROM CHECKOUT (read at another commit?): {path}:{chunk}")
                            problems += 1
                    if int(hi or lo) > n:
                        print(f"{f}: LINE PAST END ({n} lines): {path}:{lines}")
                        problems += 1
                    label = f"{path}:{chunk}" if k == 0 else chunk
                    links.append(f"[`{label}`]({url(path, lo, hi or None)})")
                changed += 1
                return ", ".join(links)

            parts[i] = REF.sub(repl, part)
        if not (a.check or a.show) and changed:
            open(f, "w", encoding="utf-8").write("".join(parts))
        print(f"{f}: {changed} references {'found' if (a.check or a.show) else 'linked'}")
    sys.exit(1 if problems else 0)


if __name__ == "__main__":
    main()
