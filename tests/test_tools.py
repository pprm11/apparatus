"""Offline tests for tools/ (no network). Run: python -I -m unittest discover -s tests"""
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
from redact import redact  # noqa: E402
from search_memory import build, catalog, search  # noqa: E402

# BLOCK: real shapes that must never reach the gateway.
BLOCK = {
    "token: ghp_ABCDEFGHIJKLMNOPQRSTUVWX1234": "ghp_",
    "senha=hunter2hunter2": "hunter2",
    "Authorization: Bearer abc123def456ghi789": "abc123",
    "api_key = 'sk-abcdefghijklmnopqrstuv'": "sk-abc",
    "AKIAABCDEFGHIJKLMNOP": "AKIA",
    "falar com joao.silva@globex.example.com": "joao.silva",
    "CPF 123.456.789-09 do lead": "123.456",
    "CPF 12345678909": "12345678909",
    "ligar (11) 98765-4321": "98765",
    "https://llm.example.com/v1/keys?token=abc": "token=abc",
    "conta AWS 123456789012": "123456789012",
    "host 10.0.12.7": "10.0.12.7",
}
# PASS: correct phrasings that must stay readable.
PASS = [
    "PR #104 no hml, card T94",
    "acme/judge-1.0 como segundo juiz",
    "ruleset 25217784 do hml",
    "secret management e token do GitHub",
    "api_key=$LITELLM_API_KEY",
    "bateria com 34 de 35 cenários",
    "ADR-0135 e commit 3e6db90",
]


class RedactTest(unittest.TestCase):
    def test_block_corpus(self) -> None:
        for text, leaked in BLOCK.items():
            with self.subTest(text=text):
                self.assertNotIn(leaked, redact(text))

    def test_pass_corpus(self) -> None:
        for text in PASS:
            with self.subTest(text=text):
                self.assertEqual(redact(text), text)


def _memory(root: str, project: str, name: str, desc: str, body: str, keywords: str = "") -> None:
    folder = os.path.join(root, "projects", project, "memory")
    os.makedirs(folder, exist_ok=True)
    kw = f"  keywords: {keywords}\n" if keywords else ""
    with open(os.path.join(folder, f"{name}.md"), "w", encoding="utf-8") as fh:
        fh.write(f"---\nname: {name}\ndescription: {desc}\nmetadata:\n{kw}  type: project\n---\n{body}\n")


class SearchTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        root = self.root = self.tmp.name
        _memory(root, "p1", "eval-gate", "modelos do eval-gate e Jev", "juiz Sonnet, Jev mede. Alex decidiu.")
        _memory(root, "p1", "railway", "deploy no Railway hml", "Alex sobe api e worker. Contato 11987654321.")
        _memory(root, "p2", "telinhas", "widgets para o Alex", "Alex gosta de telinha. Ver [[eval-gate]].")
        _memory(root, "p2", "owners", "Frozen-code owners approve agent PRs", "Sam approves.",
                keywords="codigo congelado, quem aprova, code owners")
        _memory(root, "p2", "my-harness", "harness pessoal governado por RFC", "RFC, HLA, ADR.")
        with open(os.path.join(root, "ubiquitous-language.md"), "w", encoding="utf-8") as fh:
            fh.write("| Palavra | Sentidos | Termo padrao |\n|---|---|---|\n"
                     "| brain | harness pessoal · Brain do Acme OS | **my-harness** · **Brain** |\n")

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_rare_term_beats_common_term(self) -> None:
        hits = search("alex jev", self.root, 3)
        self.assertEqual(hits[0].doc.name, "eval-gate")

    def test_accent_insensitive_and_no_match(self) -> None:
        self.assertEqual(search("júiz", self.root, 1)[0].doc.name, "eval-gate")
        self.assertEqual(search("kubernetes", self.root, 3), [])

    def test_keywords_bridge_languages(self) -> None:
        self.assertEqual(search("quem aprova codigo congelado", self.root, 1)[0].doc.name, "owners")

    def test_glossary_alias_expands_query(self) -> None:
        self.assertEqual(search("governanca do brain", self.root, 1)[0].doc.name, "my-harness")

    def test_index_has_backlinks_and_catalog_lists_missing_keywords(self) -> None:
        index = build(self.root)
        eval_gate = next(e for e in index["docs"] if e["name"] == "eval-gate")
        self.assertEqual(eval_gate["backlinks"], ["telinhas"])
        text = catalog(index)
        self.assertIn("Linked from: telinhas", text)
        self.assertIn("eval-gate, my-harness, railway, telinhas", text.split("## Memories without keywords")[1])

    def test_build_skips_when_current_and_stores_a_short_body(self) -> None:
        import json
        import time
        from search_memory import write_index
        out = os.path.join(self.root, "out")
        index_path, catalog_path = os.path.join(out, "i.json"), os.path.join(out, "INDEX.md")
        _memory(self.root, "p2", "long", "texto longo", "palavra " * 300)
        _, rebuilt = write_index(self.root, index_path=index_path, catalog_path=catalog_path)
        self.assertTrue(rebuilt)
        with open(index_path, encoding="utf-8") as fh:
            stored = json.load(fh)
        self.assertTrue(all(len(e["body"]) <= 400 for e in stored["docs"]))
        long_entry = next(e for e in stored["docs"] if e["name"] == "long")
        self.assertIn("palavra", long_entry["tf"])  # tf was computed from the whole body
        before = os.path.getmtime(index_path)
        _, rebuilt = write_index(self.root, index_path=index_path, catalog_path=catalog_path)
        self.assertFalse(rebuilt)
        self.assertEqual(os.path.getmtime(index_path), before)
        _, rebuilt = write_index(self.root, force=True, index_path=index_path, catalog_path=catalog_path)
        self.assertTrue(rebuilt)
        # a newer source triggers a rebuild
        later = time.time() + 5
        src = os.path.join(self.root, "projects", "p1", "memory", "railway.md")
        os.utime(src, (later, later))
        _, rebuilt = write_index(self.root, index_path=index_path, catalog_path=catalog_path)
        self.assertTrue(rebuilt)
        # a removed source triggers a rebuild too
        os.remove(os.path.join(self.root, "projects", "p2", "memory", "long.md"))
        _, rebuilt = write_index(self.root, index_path=index_path, catalog_path=catalog_path)
        self.assertTrue(rebuilt)

    def test_newer_glossary_does_not_make_the_index_stale_forever(self) -> None:
        import time
        from search_memory import write_index
        now = time.time()
        for path, _ in __import__("search_memory").sources(self.root):
            os.utime(path, (now - 100, now - 100))
        os.utime(os.path.join(self.root, "ubiquitous-language.md"), (now - 50, now - 50))
        out = os.path.join(self.root, "out")
        paths = dict(index_path=os.path.join(out, "i.json"), catalog_path=os.path.join(out, "INDEX.md"))
        self.assertTrue(write_index(self.root, **paths)[1])
        self.assertFalse(write_index(self.root, **paths)[1])


class ExtractPromptsTest(unittest.TestCase):
    def test_bad_timestamps_are_skipped_and_only_user_lines_are_parsed(self) -> None:
        import contextlib
        import io
        import json
        import extract_prompts
        lines = [
            {"type": "user", "timestamp": "not-a-date", "message": {"content": "bad ts"}},
            {"type": "assistant", "timestamp": "2026-10-20T10:00:00Z", "message": {"content": "reply"}},
            {"type": "user", "timestamp": "2026-10-20T10:00:00Z", "message": {"content": "good prompt"}},
            {"type": "user", "timestamp": "2026-01-01T10:00:00Z", "message": {"content": "too old"}},
        ]
        with tempfile.TemporaryDirectory() as tmp:
            folder = os.path.join(tmp, "proj")
            os.makedirs(folder)
            with open(os.path.join(folder, "abcdefgh.jsonl"), "w", encoding="utf-8") as fh:
                fh.write("\n".join(json.dumps(x) for x in lines))
            argv = ["x", "--since", "2026-10-01", "--root", tmp, "--codex-root", ""]
            out = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
            with mock.patch.object(sys, "argv", argv), contextlib.redirect_stdout(out):
                extract_prompts.main()
        out.flush()
        text = out.buffer.getvalue().decode("utf-8")
        self.assertIn("good prompt", text)
        for absent in ("bad ts", "too old", "reply"):
            self.assertNotIn(absent, text)
        self.assertFalse(extract_prompts.is_user_line('{"type":"assistant"}'))
        self.assertIsNone(extract_prompts.parse_ts("garbage"))


if __name__ == "__main__":
    unittest.main()
