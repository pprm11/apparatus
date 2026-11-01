"""The tree is English only: file names and text. A small allowlist covers data the tools need (Portuguese keyword
lists for matching user text, legacy names the migration maps) and files that must quote Portuguese on purpose.

The check is a heuristic, not a language detector: an accented Latin letter, or three distinct Portuguese function
words in one line, is a hit."""
import re
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEXT = {".md", ".py", ".sh", ".ps1", ".json", ".yml", ".yaml", ".txt", ".toml", ".html", ".js", ".mjs", ".css", ".cfg"}
ACCENT = re.compile("[áàâãéêíóôõúç]", re.I)
WORDS = re.compile(r"\b(não|você|uma|isso|quando|também|então|são|está|pelo|pela|dos|das|ainda|sempre|nunca|porque|"
                   r"para|com|que|mais|seu|sua|ele|ela|esse|essa|este|esta|como|onde)\b", re.I)
FILE_WORDS = re.compile(r"(^|[-_/.])(regra|regras|padroes|padrao|glossario|sessao|instalar|caixa|mapa|contexto|"
                        r"usuario|empresa|projeto|chave|medicoes|orfao)($|[-_/.])", re.I)

# path prefix -> why Portuguese is allowed there
ALLOW = {
    "CHANGELOG.md": "records the old Portuguese names in the rename table",
    "tools/renames.json": "the old names the migration maps",
    "tools/migrate.py": "legacy marker names",
    "tools/onboard.py": "legacy header of installs made before the rename",
    "tools/learn.py": "Portuguese keyword lists (STOP_PT, CORRECTION_PT, ...) used to match what users type",
    "tools/search_memory.py": "STOPWORDS_PT keyword list",
    "tools/lint_glossary.py": "legacy Portuguese headings accepted as aliases",
    "tools/lint_memory.py": "legacy schema file name",
    "tools/render_harness.py": "legacy generated-file markers",
    "superego/scripts/hook-prompt-guard.py": "PING_PHRASES_PT keyword list",
    "ci/": "the deny patterns name Portuguese terms and accented spellings on purpose",
    "kits/collective/ci/": "the deny patterns name Portuguese terms on purpose",
    "tests/test_generic.py": "forbidden-name regex with accented spellings",
    "tests/test_english_only.py": "this file",
    "tests/test_migrate.py": "legacy names",
    "tests/test_learn.py": "fixtures for the Portuguese keyword lists",
    "tests/test_contract.py": "pattern names",
    "docs/ci-gates.md": "quotes the deny patterns",
}


def allowed(rel: str) -> bool:
    return any(rel == p or rel.startswith(p) for p in ALLOW if p.endswith("/") or rel == p)


class EnglishOnlyTest(unittest.TestCase):
    def tracked(self) -> list[str]:
        out = subprocess.run(["git", "-C", str(ROOT), "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
                             capture_output=True, text=True, encoding="utf-8")
        if out.returncode != 0:
            self.skipTest("not a git checkout")
        return [p for p in out.stdout.split("\0") if p and (ROOT / p).exists()]

    def test_file_and_folder_names_are_english(self) -> None:
        bad = [p for p in self.tracked() if (ACCENT.search(p) or FILE_WORDS.search(p)) and not allowed(p)]
        self.assertEqual(bad, [], "Portuguese in a file or folder name:\n" + "\n".join(bad))

    def test_text_is_english(self) -> None:
        hits: list[str] = []
        for rel in self.tracked():
            if Path(rel).suffix not in TEXT or allowed(rel):
                continue
            try:
                lines = (ROOT / rel).read_text(encoding="utf-8").splitlines()
            except (UnicodeDecodeError, OSError):
                continue
            for n, line in enumerate(lines, 1):
                if ACCENT.search(line) or len({m.lower() for m in WORDS.findall(line)} & PT_ONLY) >= 3:
                    hits.append(f"{rel}:{n}: {line.strip()[:80]}")
        self.assertEqual(hits, [], "Portuguese in the tree (translate it, or allow the file with a reason):\n" + "\n".join(hits[:60]))

    def test_every_allowlist_entry_still_exists(self) -> None:
        stale = [p for p in ALLOW if not ((ROOT / p).exists())]
        self.assertEqual(stale, [], f"allowlist entries that no longer exist: {stale}")


# Words that are Portuguese and not English: "com", "para", "que" and similar are excluded from the 3-word count
# because they appear in English text and code (domain names, variable names).
PT_ONLY = {"não", "você", "uma", "isso", "quando", "também", "então", "são", "está", "pelo", "pela", "dos", "das",
           "ainda", "sempre", "nunca", "porque", "seu", "sua", "esse", "essa", "este", "esta", "onde", "mais", "como"}

if __name__ == "__main__":
    unittest.main()
