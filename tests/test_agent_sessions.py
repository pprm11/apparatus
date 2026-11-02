"""Harvest must survive odd Codex rollouts: valid-JSON lines that are not objects, compressed rollouts."""
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import agent_sessions  # noqa: E402
import codex_sessions  # noqa: E402

META = json.dumps({"type": "session_meta", "payload": {"id": "sid-1", "cwd": "/w"}})
REPLY = json.dumps({"type": "response_item", "payload": {
    "type": "message", "role": "assistant", "content": [{"type": "output_text", "text": "done?"}]}})


class CodexTailTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def rollout(self, *lines, name="r.jsonl", raw=None):
        path = os.path.join(self.tmp.name, name)
        with open(path, "wb") as fh:
            fh.write(raw if raw is not None else ("\n".join(lines) + "\n").encode())
        return path

    def test_non_object_json_lines_are_skipped(self):
        path = self.rollout(META, "4", "[1, 2]", '"text"', "null", REPLY, "7")
        self.assertEqual(agent_sessions._codex_tail(path), ("sid-1", "/w", "done?"))

    def test_non_object_first_line_is_skipped(self):
        path = self.rollout("3", REPLY)
        self.assertEqual(agent_sessions._codex_tail(path), ("", "", "done?"))

    def test_compressed_rollout_has_no_tail_and_does_not_raise(self):
        # zstd magic followed by bytes whose lines parse as bare numbers, as in a real archived rollout
        path = self.rollout(name="r.jsonl.zst", raw=b"\x28\xb5\x2f\xfd\n4\n1\n3\n")
        self.assertEqual(agent_sessions._codex_tail(path), ("", "", ""))

    def test_one_bad_rollout_does_not_fail_the_listing(self):
        home = os.path.join(self.tmp.name, "codex")
        os.makedirs(os.path.join(home, "sessions"))
        with open(os.path.join(home, "session_index.jsonl"), "w") as fh:
            fh.write('5\n{"id": "sid-1", "thread_name": "T"}\n')
        with open(os.path.join(home, "sessions", "a.jsonl"), "w") as fh:
            fh.write(META + "\n9\n" + REPLY + "\n")
        found = list(agent_sessions.codex_sessions(home))
        self.assertEqual([(s.id, s.title, s.status) for s in found], [("sid-1", "T", "waiting")])

    def test_codex_transcript_reader_skips_non_object_lines(self):
        path = self.rollout(META, "4", REPLY)
        self.assertEqual([r["role"] for r in codex_sessions.iter_file(path)], ["assistant"])


if __name__ == "__main__":
    unittest.main()
