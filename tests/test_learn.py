"""Offline tests for the self-learning loop: signals, clustering, routing, budget and before/after effect."""
import json
import os
import sys
import tempfile
import time
import unittest
from datetime import date, timedelta
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
import agent_sessions  # noqa: E402
import decisions  # noqa: E402
import learn  # noqa: E402

NOW = time.time()
PROMPTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "prompts")


def claude_line(role: str, text: str, ts: str) -> str:
    content = text if role == "user" else [{"type": "text", "text": text}]
    return json.dumps({"type": role, "timestamp": ts, "message": {"content": content}})


def make_session(tmp: str, sid: str, turns: list[tuple[str, str, str]], cwd: str = "C:\\Codes\\proj") -> agent_sessions.Session:
    path = os.path.join(tmp, f"{sid}.jsonl")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(claude_line(r, t, ts) for ts, r, t in turns))
    return agent_sessions.Session("claude", sid, sid, cwd, "open", NOW, path)


def iso(days_ago: float) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(NOW - days_ago * 86400))


class Env(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.home = os.path.join(self.tmp, "home")
        self.repo = os.path.join(self.tmp, "repo")
        os.makedirs(os.path.join(self.home, "projects", "C--Codes-proj", "memory"))
        os.makedirs(os.path.join(self.repo, "prompts"))
        for f in ("learn-classify.md", "learn-propose.md"):
            with open(os.path.join(PROMPTS, f), encoding="utf-8") as src, \
                    open(os.path.join(self.repo, "prompts", f), "w", encoding="utf-8") as dst:
                dst.write(src.read())
        with open(os.path.join(self.repo, "proposals.md"), "w", encoding="utf-8") as fh:
            fh.write("# Proposals\n")
        patcher = mock.patch.object(learn, "REPO", self.repo)
        patcher.start()
        self.addCleanup(patcher.stop)

    def sessions(self):
        t1 = [(iso(5), "user", "sempre escreve o resumo final com tabela de custos por modelo antes de commitar"),
              (iso(5), "assistant", "Quer a opção A ou B?"),
              (iso(5), "user", "1A, aprovado"),
              (iso(4), "user", "não, faz o resumo final com tabela de custos por modelo antes de commitar"),
              (iso(3), "user", "coloca a tabela de custos por modelo no resumo final antes de commitar de novo")]
        t2 = [(iso(2), "user", "resumo final com tabela de custos por modelo, antes de commitar por favor")]
        return [make_session(self.tmp, "s1", t1), make_session(self.tmp, "s2", t2)]


class SignalTest(Env):
    def test_kinds_and_decision_context(self):
        sigs = learn.extract(self.home, learn.load_state(self.home), 30, self.sessions())
        kinds = [s["kind"] for s in sigs]
        self.assertEqual(kinds.count("decision"), 1)
        self.assertEqual(kinds.count("correction"), 1)
        dec = next(s for s in sigs if s["kind"] == "decision")
        self.assertIn("opção A ou B", dec["ctx"])

    def test_incremental_and_meta_sessions_skipped(self):
        state, sess = learn.load_state(self.home), self.sessions()
        self.assertTrue(learn.extract(self.home, state, 30, sess))
        self.assertEqual(learn.extract(self.home, state, 30, sess), [])  # watermark: nothing new
        layer = os.path.join(self.tmp, "ego-layer")
        meta = make_session(self.tmp, "m", [(iso(1), "user", "não, faz de novo o relatório do contexto")], cwd=layer)
        with mock.patch.object(learn, "layer_dirs", return_value=[os.path.normcase(layer)]):
            self.assertEqual(learn.extract(self.home, learn.load_state(self.home), 30, [meta]), [])

    def test_secrets_are_redacted_in_the_ledger(self):
        s = make_session(self.tmp, "x", [(iso(1), "user", "usa a senha: hunter2hunter2 e o email a.b" + "@" + "cliente.com na config")])
        sig = learn.extract(self.home, learn.load_state(self.home), 30, [s])[0]
        self.assertNotIn("hunter2", sig["text"])
        self.assertNotIn("cliente.com", sig["text"])


class ClusterTest(Env):
    def test_repeat_across_days_becomes_candidate_unless_covered(self):
        sigs = learn.extract(self.home, learn.load_state(self.home), 30, self.sessions())
        cands = learn.cluster(sigs, set())
        self.assertEqual(len(cands), 1)
        self.assertEqual(cands[0]["kind"], "repeat")
        self.assertGreaterEqual(cands[0]["n"], 3)
        covered = {"resumo", "final", "tabela", "custos", "modelo", "antes", "commitar"}
        self.assertEqual(learn.cluster(sigs, covered), [])

    def test_one_day_is_not_a_repeat(self):
        s = make_session(self.tmp, "d", [(iso(1), "user", f"gera o relatório mensal de vendas por região agora {i}") for i in range(4)])
        sigs = learn.extract(self.home, learn.load_state(self.home), 30, [s])
        self.assertEqual(learn.cluster(sigs, set()), [])


def fake_runner(calls):
    def run(prompt, model, budget, read_tools):
        calls.append((model, budget, read_tools))
        data = json.loads(prompt[prompt.index("{\n"):prompt.rindex("}") + 1])
        if model == "haiku":
            rep = [{"id": r["id"], "real": True} for r in data["repeats"]]
            dec = [{"id": d["id"], "route": "memory", "title": "t", "fact": "f"} for d in data["decisions"]]
            return json.dumps({"repeats": rep, "decisions": dec}), 0.01
        props = [{"id": r["id"], "title": "Resumo final com custos", "kind": "rule",
                  "to": "~/.claude/rules/summary.md", "level": "id", "why": "asked 3 times"} for r in data["repeats"]]
        mems = [{"decision_id": d["id"], "slug": "decisao-teste", "title": "Decisão teste", "description": "desc",
                 "keywords": "a, b", "type": "project", "body": "Fato. **Why:** x. **How to apply:** y."} for d in data["decisions"]]
        return json.dumps({"proposals": props, "memories": mems}), 0.05
    return run


class RunTest(Env):
    def test_dry_run_writes_nothing_and_calls_no_model(self):
        calls = []
        rep = learn.run(self.home, 30, True, True, fake_runner(calls), self.sessions(), self.repo)
        self.assertEqual(calls, [])
        self.assertEqual(rep["model"], "dry-run")
        self.assertFalse(os.path.exists(os.path.join(learn.learn_dir(self.home), "signals.jsonl")))
        with open(os.path.join(self.repo, "proposals.md"), encoding="utf-8") as fh:
            self.assertEqual(fh.read(), "# Proposals\n")

    def test_full_run_routes_proposal_memory_and_respects_budget(self):
        calls = []
        rep = learn.run(self.home, 30, False, True, fake_runner(calls), self.sessions(), self.repo)
        self.assertEqual([c[0] for c in calls], ["haiku", "sonnet"])
        self.assertLessEqual(sum(c[1] for c in calls), learn.BUDGET_RUN + 0.001)
        self.assertEqual(len(rep["proposals"]), 1)
        with open(os.path.join(self.repo, "proposals.md"), encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("Status: open", text)
        self.assertIn("Source: learn", text)
        self.assertEqual(rep["memories"], ["decisao-teste"])
        self.assertTrue(os.path.isfile(os.path.join(self.home, "projects", "C--Codes-proj", "memory", "decisao-teste.md")))
        self.assertAlmostEqual(learn.spent_today(learn.load_state(self.home)), 0.06, places=2)
        again = learn.run(self.home, 30, False, True, fake_runner(calls), self.sessions(), self.repo)
        self.assertEqual(len(calls), 2)  # nothing new: the model is not asked again
        self.assertEqual(again["proposals"], [])

    def test_daily_budget_stops_model_calls(self):
        state = learn.load_state(self.home)
        state["spend"][date.today().isoformat()] = learn.BUDGET_DAY
        learn.save_state(self.home, state)
        calls = []
        rep = learn.run(self.home, 30, False, True, fake_runner(calls), self.sessions(), self.repo)
        self.assertEqual(calls, [])
        self.assertEqual(rep["proposals"], [])

    def test_candidates_the_model_rejected_are_not_asked_again(self):
        def no(prompt, model, budget, read_tools):
            return json.dumps({"repeats": [{"id": "x", "real": False}], "decisions": []}), 0.01
        learn.run(self.home, 30, False, True, no, self.sessions(), self.repo)
        state = learn.load_state(self.home)
        self.assertEqual(len(state["rejected"]), 1)
        sigs = learn.load_ledger(self.home)
        cand = learn.cluster(sigs, set())[0]
        self.assertTrue(learn.already_proposed(cand, state))

    def test_inbox_route_dedupes_by_key(self):
        sig = {"id": "abc", "harness": "claude", "session": "s", "text": "1A"}
        self.assertTrue(learn.route_inbox(self.home, {"title": "x", "fact": "y"}, sig))
        self.assertEqual(learn.route_inbox(self.home, {"title": "x", "fact": "y"}, sig), "")
        self.assertEqual(len(decisions.load(self.home)["items"]), 1)


class MemoryRoutingTest(Env):
    def runner(self, project):
        base = fake_runner([])

        def run(prompt, model, budget, read_tools):
            text, cost = base(prompt, model, budget, read_tools)
            data = json.loads(text)
            for m in data.get("memories", []):
                m["project"] = project
            return json.dumps(data), cost
        return run

    def test_model_can_file_memory_under_another_existing_project(self):
        other = os.path.join(self.home, "projects", "C--Codes-other", "memory")
        os.makedirs(other)
        rep = learn.run(self.home, 30, False, True, self.runner("C--Codes-other"), self.sessions(), self.repo)
        self.assertEqual(rep["memories"], ["decisao-teste"])
        self.assertTrue(os.path.isfile(os.path.join(other, "decisao-teste.md")))

    def test_unknown_project_falls_back_to_the_session_project(self):
        learn.run(self.home, 30, False, True, self.runner("C--Nope"), self.sessions(), self.repo)
        self.assertTrue(os.path.isfile(os.path.join(self.home, "projects", "C--Codes-proj", "memory", "decisao-teste.md")))
        self.assertFalse(os.path.exists(os.path.join(self.home, "projects", "C--Nope")))

    def test_duplicate_of_existing_memory_is_not_written(self):
        folder = os.path.join(self.home, "projects", "C--Codes-proj", "memory")
        with open(os.path.join(folder, "ja-existe.md"), "w", encoding="utf-8") as fh:
            fh.write("\n".join(["---", "name: ja-existe", "description: desc", "metadata:", "  keywords: a, b", "---",
                                "Decisão teste desc a b Fato. Why: x. How to apply: y.", ""]))
        rep = learn.run(self.home, 30, False, True, self.runner("C--Codes-proj"), self.sessions(), self.repo)
        self.assertEqual(rep["memories"], [])
        self.assertFalse(os.path.exists(os.path.join(folder, "decisao-teste.md")))
        self.assertTrue(learn.find_duplicate(self.home, {"title": "Decisão teste", "description": "desc", "keywords": "a, b",
                                                         "body": "Fato. Why: x. How to apply: y."}))


class LevelTest(Env):
    def test_memory_proposal_and_inbox_carry_the_level(self):
        calls = []
        base = fake_runner(calls)

        def run(prompt, model, budget, read_tools):
            text, cost = base(prompt, model, budget, read_tools)
            data = json.loads(text)
            for m in data.get("memories", []):
                m["level"] = "superego"
            for d in data.get("decisions", []):
                d["level"] = "id"
            return json.dumps(data), cost
        learn.run(self.home, 30, False, True, run, self.sessions(), self.repo)
        memory = os.path.join(self.home, "projects", "C--Codes-proj", "memory", "decisao-teste.md")
        with open(memory, encoding="utf-8") as fh:
            self.assertIn("level: superego", fh.read())
        with open(os.path.join(self.repo, "proposals.md"), encoding="utf-8") as fh:
            self.assertIn("Level: id", fh.read())

    def test_unknown_level_falls_back_to_default(self):
        self.assertEqual(learn.level_of({"level": "galaxy"}), "ego")
        sig = {"id": "lv", "harness": "claude", "session": "s", "text": "x"}
        learn.route_inbox(self.home, {"title": "t", "fact": "f", "level": "id"}, sig)
        self.assertEqual(decisions.load(self.home)["items"][0]["level"], "id")

    def test_ego_dir_prefers_env_then_manifest(self):
        with mock.patch.dict(os.environ, {"LEARN_EGO": "X:/ego"}):
            self.assertEqual(learn.ego_dir(), "X:/ego")
        man = os.path.join(self.tmp, "manifest.json")
        ego = os.path.join(self.tmp, "ego")
        with open(man, "w", encoding="utf-8") as fh:
            json.dump({"default_level": "ego", "layers": [{"level": "ego", "path": ego, "active": True}]}, fh)
        with mock.patch.dict(os.environ, {"LEARN_EGO": ""}):
            self.assertEqual(os.path.normcase(learn.ego_dir(man)), os.path.normcase(ego))


class EffectTest(Env):
    def proposal(self, status: str, applied: str):
        state = learn.load_state(self.home)
        core = ["resumo", "final", "tabela", "custos", "modelo", "commitar"]
        state["proposed"].append({"id": "c1", "core": core, "date": "2026-10-01", "proposal": "P-1-L1", "kind": "repeat", "applied": applied})
        learn.save_state(self.home, state)
        with open(os.path.join(self.repo, "proposals.md"), "w", encoding="utf-8") as fh:
            fh.write(f"### P-1-L1 · t\n{status}\n")
        return core

    def test_before_after_verdict(self):
        approved = date.today() - timedelta(days=20)
        core = self.proposal("Status: approved (18/10)", approved.isoformat())
        learn.append_ledger(self.home, [{"id": f"b{d}", "ts": (date.today() - timedelta(days=d)).isoformat() + "T10:00",
                                         "kind": "prompt", "tokens": core} for d in (25, 24, 22)])
        row = learn.effects(self.home, self.repo)[0]
        self.assertEqual((row["before"], row["after"], row["verdict"]), (3, 0, "worked"))

    def test_recurrence_after_approval_means_it_did_not_work(self):
        approved = date.today() - timedelta(days=20)
        core = self.proposal("Status: approved (18/10)", approved.isoformat())
        days = (25, 24, 10, 9, 8)
        learn.append_ledger(self.home, [{"id": f"b{d}", "ts": (date.today() - timedelta(days=d)).isoformat() + "T10:00",
                                         "kind": "prompt", "tokens": core} for d in days])
        self.assertTrue(learn.effects(self.home, self.repo)[0]["verdict"].startswith("did not work"))

    def test_open_proposal_is_not_measured(self):
        self.proposal("Status: open", "")
        self.assertEqual(learn.effects(self.home, self.repo)[0]["verdict"], "waiting for yes")


class PathTest(Env):
    def test_claude_app_dirs_finds_local_profile(self):
        local = os.path.join(self.tmp, "Local")
        prof = os.path.join(local, "Claude-Data", "abc", "claude-code-sessions", "u", "w")
        os.makedirs(prof)
        with open(os.path.join(prof, "local_1.json"), "w", encoding="utf-8") as fh:
            json.dump({"sessionId": "local_1", "cwd": "C:\\x", "isArchived": True, "cliSessionId": "c1", "lastActivityAt": 1000}, fh)
        with mock.patch.dict(os.environ, {"LOCALAPPDATA": local}), \
                mock.patch.object(agent_sessions, "CLAUDE_APP", os.path.join(self.tmp, "none")):
            got = list(agent_sessions.claude_sessions())
        self.assertEqual([(s.id, s.status) for s in got], [("local_1", "archived")])


if __name__ == "__main__":
    unittest.main()
