"""Offline tests for the routines: session listing, decision inbox, decay, harvest digest and delegation."""
import argparse
import json
import os
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import agent_sessions  # noqa: E402
import check_codex  # noqa: E402
import decay  # noqa: E402
import decisions  # noqa: E402
import delegate  # noqa: E402
import harvest  # noqa: E402

NOW = time.time()


def write(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(text)


def session(status: str, sid: str = "s1", idle_days: float = 5, harness: str = "claude") -> agent_sessions.Session:
    return agent_sessions.Session(harness, sid, f"title {sid}", "C:\\Codes\\x", status, NOW - idle_days * 86400, "", "ask?")


class SessionsTest(unittest.TestCase):
    def test_claude_status_from_app_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as app:
            base = {"cwd": "C:\\Codes\\x", "cliSessionId": "c1", "lastActivityAt": NOW * 1000}
            cases = {
                "a": {"isArchived": True},
                "w": {"turnWrapUp": {"ask": "Which fix?"}},
                "b": {"postTurnSummary": {"status_category": "blocked"}},
                "d": {"postTurnSummary": {"status_category": "completed"}},
                "o": {},
            }
            for sid, extra in cases.items():
                write(os.path.join(app, "u", "o", f"{sid}.json"), json.dumps({**base, "sessionId": sid, **extra}))
            got = {s.id: s.status for s in agent_sessions.claude_sessions(app, "P")}
        self.assertEqual(got, {"a": "archived", "w": "waiting", "b": "waiting", "d": "done", "o": "open"})


class InboxTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.home = self.tmp.name
        self.repo = decisions.REPO
        decisions.REPO = self.home
        write(os.path.join(self.home, "proposals.md"),
              "### P-2026-10-20-1 · Card diz a DEC\nWhy: 31 pontos vieram do card\nStatus: open\n\n"
              "### P-2026-10-18-1 · Velha\nStatus: approved (18/10)\n")

    def tearDown(self) -> None:
        decisions.REPO = self.repo
        self.tmp.cleanup()

    def test_scan_adds_once_and_drops_when_the_cause_is_gone(self) -> None:
        sessions = [session("waiting", "w1"), session("done", "d1", 5), session("done", "d2", 1), session("archived", "a1")]
        added, dropped = decisions.scan(self.home, sessions, NOW)
        data = decisions.load(self.home)
        kinds = sorted(i["kind"] for i in data["items"])
        self.assertEqual((added, dropped), (3, 0))
        self.assertEqual(kinds, ["proposal", "session_archive", "session_waiting"])
        self.assertEqual(decisions.scan(self.home, sessions, NOW), (0, 0))
        decisions.scan(self.home, [session("archived", "w1"), session("done", "d1", 5)], NOW)
        status = {i["key"]: i["status"] for i in decisions.load(self.home)["items"]}
        self.assertEqual(status["waiting:claude:w1"], "dropped")
        self.assertEqual(status["archive:claude:d1"], "open")

    def test_skill_draft_installs_on_answer_a(self) -> None:
        write(os.path.join(self.home, "skill-drafts", "nova", "SKILL.md"), "---\nname: nova\n---\n")
        decisions.scan(self.home, [], NOW)
        data = decisions.load(self.home)
        draft = next(i for i in data["items"] if i["kind"] == "skill_draft")
        draft.update(status="resolved", answer="A")
        decisions.save(data, self.home)
        self.assertEqual(decisions.apply(self.home), [f"{draft['id']}: installed skill nova"])
        self.assertTrue(os.path.isfile(os.path.join(self.home, "skills", "nova", "SKILL.md")))
        self.assertEqual(decisions.apply(self.home), [])

    def test_scan_keeps_the_stamp_out_of_the_inbox_and_saves_only_on_change(self) -> None:
        sessions = [session("waiting", "w1")]
        decisions.scan(self.home, sessions, NOW)
        inbox = decisions.store_path(self.home)
        self.assertNotIn("scanned", decisions.load(self.home))
        self.assertTrue(decisions.scanned_at(self.home))
        before = os.path.getmtime(inbox)
        os.utime(inbox, (before - 100, before - 100))
        decisions.scan(self.home, sessions, NOW)
        self.assertEqual(os.path.getmtime(inbox), before - 100)  # nothing changed: file untouched
        decisions.scan(self.home, [], NOW)
        self.assertGreater(os.path.getmtime(inbox), before - 100)  # the item was dropped: saved

    def test_scan_does_not_lose_an_add_made_while_sessions_load(self) -> None:
        def slow_sessions():
            data = decisions.load(self.home)
            decisions.new_item(data, "manual", "added meanwhile")
            decisions.save(data, self.home)
            return [session("waiting", "w1")]
        with mock.patch.object(decisions.agent_sessions, "all_sessions", slow_sessions):
            decisions.scan(self.home, None, NOW)
        titles = [i["title"] for i in decisions.load(self.home)["items"]]
        self.assertIn("added meanwhile", titles)
        self.assertIn("title w1", titles)

    def test_apply_table(self) -> None:
        cases = [  # (kind, harness, answer, expected log suffix or None when it stays resolved)
            ("session_waiting", "claude", "B", None),  # needs the desktop app to archive
            ("session_archive", "claude", "A", None),
            ("session_waiting", "claude", "A", "nothing to run"),
            ("session_archive", "claude", "B", "nothing to run"),
            ("session_waiting", "codex", "A", "nothing to run"),
            ("session_archive", "codex", "B", "nothing to run"),
            ("session_archive", "codex", "A", "codex archive x1"),
            ("session_waiting", "codex", "B", "codex archive x1"),
            ("manual", "", "A", "nothing to run"),
            ("proposal", "", "A", None),  # an agent session applies proposals
            ("proposal", "", "B", None),
        ]
        for kind, harness, answer, expected in cases:
            with self.subTest(kind=kind, harness=harness, answer=answer):
                data = {"next": 2, "items": [{"id": "D-1", "kind": kind, "status": "resolved", "answer": answer,
                                              "ref": {"harness": harness, "id": "x1"}, "key": "", "title": "t"}]}
                decisions.save(data, self.home)
                fake = mock.Mock(returncode=0)
                with mock.patch.object(decisions, "codex_exe", return_value="codex"),                         mock.patch.object(decisions.subprocess, "run", return_value=fake):
                    log = decisions.apply(self.home)
                item = decisions.load(self.home)["items"][0]
                if expected is None:
                    self.assertEqual((log, item.get("applied")), ([], None))
                else:
                    self.assertEqual(log, [f"D-1: {expected}"])
                    self.assertTrue(item["applied"])

    def test_codex_archive_failure_keeps_the_item_resolved(self) -> None:
        data = {"next": 2, "items": [{"id": "D-1", "kind": "session_archive", "status": "resolved", "answer": "A",
                                      "ref": {"harness": "codex", "id": "x1"}, "key": "", "title": "t"}]}
        decisions.save(data, self.home)
        with mock.patch.object(decisions, "codex_exe", return_value=None):
            self.assertEqual(decisions.apply(self.home), [])

    def test_lock_serialises_writers_and_ids_stay_unique(self) -> None:
        import threading

        def add_many() -> None:
            for _ in range(5):
                with decisions.locked(self.home):
                    data = decisions.load(self.home)
                    decisions.new_item(data, "manual", "t")
                    decisions.save(data, self.home)

        threads = [threading.Thread(target=add_many) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        ids = [i["id"] for i in decisions.load(self.home)["items"]]
        self.assertEqual(len(ids), 40)
        self.assertEqual(len(set(ids)), 40)
        self.assertFalse(os.path.exists(decisions.store_path(self.home) + ".lock"))

    def test_lock_retries_when_windows_reports_a_deleting_lock_as_permission_denied(self) -> None:
        # Windows: O_EXCL on a lock another thread is removing raises PermissionError, not FileExistsError.
        real_open, calls = os.open, []

        def flaky_open(path, flags, *args, **kwargs):
            if str(path).endswith(".lock") and len(calls) < 3:
                calls.append(path)
                raise PermissionError(13, "Permission denied", path)
            return real_open(path, flags, *args, **kwargs)

        with mock.patch.object(os, "open", flaky_open):
            with decisions.locked(self.home):
                pass
        self.assertEqual(len(calls), 3)
        self.assertFalse(os.path.exists(decisions.store_path(self.home) + ".lock"))

    def test_stale_lock_is_cleaned_and_a_busy_one_times_out(self) -> None:
        lock = decisions.store_path(self.home) + ".lock"
        write(lock, "")
        old = time.time() - decisions.LOCK_STALE - 5
        os.utime(lock, (old, old))
        with decisions.locked(self.home):
            pass  # the dead process's lock did not block us
        write(lock, "")
        with mock.patch.object(decisions, "LOCK_WAIT", 0.2):
            with self.assertRaises(TimeoutError):
                with decisions.locked(self.home):
                    pass
        os.remove(lock)

    def test_html_follows_the_artifact_contract(self) -> None:
        decisions.scan(self.home, [session("waiting", "w1")], NOW)
        page = decisions.render_html(decisions.load(self.home))
        self.assertTrue(page.startswith("<title>Decision inbox</title>"))
        for banned in ("<!doctype", "<html", "<body"):
            self.assertNotIn(banned, page.lower())
        self.assertIn('prefers-color-scheme:dark', page)
        self.assertIn("title w1", page)


class DecayTest(unittest.TestCase):
    def test_retention_falls_with_time_and_rises_with_use(self) -> None:
        self.assertGreater(decay.retention(10, 0, 45), decay.retention(60, 0, 45))
        self.assertGreater(decay.retention(60, 10, 45), decay.retention(60, 0, 45))
        self.assertAlmostEqual(decay.retention(0, 0, 45), 1.0)

    def test_protected_items_never_decay_and_archive_is_reversible(self) -> None:
        with tempfile.TemporaryDirectory() as home:
            mem = os.path.join(home, "projects", "P", "memory")
            write(os.path.join(mem, "MEMORY.md"), "- [Old](old.md) — x\n- [Fb](fb.md) — y\n")
            write(os.path.join(mem, "old.md"), "---\nname: old\nmetadata:\n  type: project\n  modified: 2026-01-01\n---\nfato\n")
            write(os.path.join(mem, "fb.md"), "---\nname: fb\nmetadata:\n  type: feedback\n---\nregra\n")
            write(os.path.join(home, "skills", "used", "SKILL.md"), "x")
            rows = decay.score(home, used={("skill", "used"): (5, NOW)}, now=NOW)
            names = {r["name"]: r for r in rows}
            self.assertNotIn("fb", names)
            self.assertLess(names["old"]["score"], decay.DORMANT)
            self.assertGreater(names["used"]["score"], 0.99)
            decay.archive(os.path.join(mem, "old.md"), "memory", home)
            self.assertTrue(os.path.isfile(os.path.join(home, "archive", "memory", "P", "old.md")))
            with open(os.path.join(mem, "MEMORY.md"), encoding="utf-8") as fh:
                self.assertEqual(fh.read(), "- [Fb](fb.md) — y\n")
            with open(os.path.join(home, "archive", "TOMBSTONES.md"), encoding="utf-8") as fh:
                self.assertIn("old.md", fh.read())

    def test_usage_counts_sessions_from_both_harnesses(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            a = os.path.join(tmp, "a.jsonl")
            b = os.path.join(tmp, "b.jsonl")
            write(a, '{"name":"Skill","input":{"skill":"humanize"}} {"file_path":"C:/x/memory/fato-um.md"}\n')
            write(b, '{"cmd":"cat C:\\\\' + 'Users\\\\p\\\\.claude\\\\skills\\\\humanize\\\\SKILL.md"}\n')
            used = decay.usage([a, b])
        self.assertEqual(used[("skill", "humanize")][0], 2)
        self.assertEqual(used[("memory", "fato-um")][0], 1)

    def test_usage_cache_skips_unchanged_transcripts_and_dry_run_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            a = os.path.join(tmp, "a.jsonl")
            write(a, '{"skill":"humanize"}\n{"x":"memory/fato-um.md"}\n')
            cache = os.path.join(tmp, "state", "decay-cache.json")
            first = decay.usage([a], cache, write_cache=False)
            self.assertFalse(os.path.exists(cache))  # dry run
            self.assertEqual(first[("skill", "humanize")][0], 1)
            decay.usage([a], cache)
            self.assertTrue(os.path.isfile(cache))
            with mock.patch.object(decay, "_names_in", side_effect=AssertionError("read again")):
                again = decay.usage([a], cache)  # same mtime and size: served from the cache
            self.assertEqual(again, first)
            write(a, '{"skill":"other-skill"}\n')
            changed = decay.usage([a], cache)
            self.assertIn(("skill", "other-skill"), changed)
            self.assertNotIn(("skill", "humanize"), changed)


class HarvestTest(unittest.TestCase):
    def test_digest_redacts_and_caps(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "t.jsonl")
            lines = [{"type": "user", "message": {"content": "token: ghp_ABCDEFGHIJKLMNOPQRSTUVWX1234 and run"}},
                     {"type": "assistant", "message": {"content": [{"type": "text", "text": "x" * 5000}]}}]
            write(path, "\n".join(json.dumps(x) for x in lines))
            s = agent_sessions.Session("claude", "s", "T", "C:\\Codes\\x", "archived", NOW, path)
            text = harvest.digest(s)
        self.assertNotIn("ghp_ABC", text)
        self.assertIn("[...cut, 5000 chars]", text)
        self.assertIn("C--Codes-x", text)


class DelegateTest(unittest.TestCase):
    def test_child_cannot_delegate_again(self) -> None:
        os.environ["DELEGATE_DEPTH"] = "1"
        try:
            args = argparse.Namespace(to="claude", brief="x", brief_file=None, cwd=".", write=False, tier="mid",
                                      budget=None, timeout=1, background=False)
            with self.assertRaises(SystemExit):
                delegate.start(args)
        finally:
            del os.environ["DELEGATE_DEPTH"]

    def test_read_only_claude_child_gets_no_edit_tools_and_a_budget(self) -> None:
        argv = delegate.build_command("claude", ".", "cheap", False, 0.5, "last.md")
        self.assertIn("haiku", argv)
        self.assertIn("0.5", argv)
        self.assertNotIn("Edit", argv)
        self.assertNotIn("Bash", argv)  # bare Bash would allow any command
        self.assertEqual([t for t in argv if t.startswith("Bash(")],
                         ["Bash(git diff:*)", "Bash(git log:*)", "Bash(git show:*)", "Bash(ls:*)"])
        self.assertIn("Bash", delegate.build_command("claude", ".", "mid", True, 2, "last.md"))
        self.assertIn("Edit", delegate.build_command("claude", ".", "mid", True, 2, "last.md"))


class TailAndRedactTest(unittest.TestCase):
    def test_codex_tail_reads_meta_from_the_first_line_and_the_answer_from_the_end(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "r.jsonl")
            meta = {"type": "session_meta", "payload": {"id": "sid1", "cwd": "C:/x"}}
            old = {"type": "response_item", "payload": {"type": "message", "role": "assistant",
                                                       "content": [{"type": "output_text", "text": "old answer"}]}}
            new = {"type": "response_item", "payload": {"type": "message", "role": "assistant",
                                                       "content": [{"type": "output_text", "text": "last answer?"}]}}
            filler = json.dumps({"type": "event", "payload": {"type": "x", "pad": "p" * 1000}})
            lines = [json.dumps(meta), json.dumps(old)] + [filler] * 100 + [json.dumps(new)]
            write(path, "\n".join(lines) + "\n")
            self.assertEqual(agent_sessions._codex_tail(path), ("sid1", "C:/x", "last answer?"))
            write(path, "\n".join([json.dumps(meta), json.dumps(old)] + [filler] * 100) + "\n")  # answer beyond the tail
            self.assertEqual(agent_sessions._codex_tail(path), ("sid1", "C:/x", ""))

    def test_digest_and_prompts_share_the_full_redaction(self) -> None:
        import extract_prompts
        text = "mail joao@globex.example.com cpf 123.456.789-09 em https://git.example.com/x"
        self.assertIs(extract_prompts.redact, harvest.redact)
        out = harvest.redact(text)
        for leaked in ("joao@", "123.456", "/x"):
            self.assertNotIn(leaked, out)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "t.jsonl")
            write(path, json.dumps({"type": "user", "message": {"content": text}}))
            s = agent_sessions.Session("claude", "s", "T", "C:/Codes/x", "archived", NOW, path)
            self.assertNotIn("joao@", harvest.digest(s))

    def test_all_sessions_is_listed_once_per_process(self) -> None:
        harvest._SESSIONS = None
        with mock.patch.object(agent_sessions, "all_sessions", return_value=[]) as listing:
            harvest.archived()
            harvest.archived()
        harvest._SESSIONS = None
        self.assertEqual(listing.call_count, 1)


class CheckCodexTest(unittest.TestCase):
    def test_failing_canary_adds_one_open_item_only(self) -> None:
        with tempfile.TemporaryDirectory() as home:
            self.assertTrue(check_codex.raise_item(["a: x"], home))
            self.assertFalse(check_codex.raise_item(["a: x"], home))
            data = decisions.load(home)
            data["items"][0]["status"] = "resolved"
            decisions.save(data, home)
            self.assertTrue(check_codex.raise_item(["a: x"], home))  # old one closed: a new one is fair
            self.assertEqual(len(decisions.load(home)["items"]), 2)


if __name__ == "__main__":
    unittest.main()
