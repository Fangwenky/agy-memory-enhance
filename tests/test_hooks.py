"""End-to-end: run the real hook scripts as subprocesses against synthetic transcripts."""
import json
import os
import tempfile
import time
import unittest

from helpers import checkpoint, model, run_hook, tool, user, write_transcript

from agymem import ledger as L
from agymem.store import Store


class HookE2ETest(unittest.TestCase):
    def setUp(self):
        self.ws = tempfile.mkdtemp()
        self.tp = os.path.join(tempfile.mkdtemp(), "transcript_full.jsonl")
        open(self.tp, "w").close()
        self.mem = os.path.join(self.ws, ".agy-memory")

    def payload(self, event, conv="c1", **kw):
        return {"hookEventName": event, "conversationId": conv, "workspacePaths": [self.ws],
                "transcriptPath": self.tp, "cwd": self.ws, "modelName": "m-test", **kw}

    def events(self):
        return Store(self.mem).read("events.jsonl")

    def texts(self, out):
        return [s["systemMessage"]["systemMessage"] for s in out.get("injectSteps", [])]

    def add_ledger(self, *entries):
        Store(self.mem).ensure().append_many("ledger.jsonl", list(entries))

    def test_full_flow(self):
        # new session: intro without brief (ledger empty) + shim generated
        out = run_hook("session_start", self.payload("SessionStart"))
        t = self.texts(out)
        self.assertEqual(len(t), 1)
        self.assertIn(".agy-memory/bin/mem", t[0])
        self.assertTrue(os.access(os.path.join(self.mem, "bin", "mem"), os.X_OK))

        write_transcript(self.tp, [user(0, "约束：不要修改 src/"), model(1, 20000)])
        self.assertEqual(run_hook("pre_invocation", self.payload("PreInvocation")), {})
        self.assertIn("约束：不要修改 src/",
                      [e["data"].get("text") for e in self.events() if e["kind"] == "user_input"])

        self.add_ledger(L.new_entry("constraint", "不要修改 src/", "c1"))
        write_transcript(self.tp, [tool(2), model(3, 1000, 500000), tool(4),
                                   checkpoint(5, 501000), model(6, 30000)])
        t = self.texts(run_hook("pre_invocation", self.payload("PreInvocation")))
        self.assertEqual(len(t), 1)
        self.assertIn("compaction #1 in this session detected (signal: checkpoint)", t[0])
        self.assertIn("不要修改 src/", t[0])
        comp = [e for e in self.events() if e["kind"] == "compaction"]
        self.assertEqual(len(comp), 1)
        self.assertIn("Resuming from a compaction", comp[0]["data"]["summary"])
        models = Store(self.mem).load_json("state", "models.json")
        self.assertEqual(models, {"m-test": 501000})

        # align is injected once only
        write_transcript(self.tp, [model(7, 31000)])
        self.assertEqual(run_hook("pre_invocation", self.payload("PreInvocation")), {})

        # learned soft limit: 0.75 * 501000 = 375750
        write_transcript(self.tp, [model(8, 0, 380000)])
        t = self.texts(run_hook("pre_invocation", self.payload("PreInvocation")))
        self.assertEqual(len(t), 1)
        self.assertIn("Context is ~380k", t[0])

    def test_resumed_session_without_session_start(self):
        self.add_ledger(L.new_entry("decision", "use sqlite", "old"))
        write_transcript(self.tp, [user(0, "x"), model(1, 0, 300000), checkpoint(2, 300000),
                                   model(3, 20000)])
        t = self.texts(run_hook("pre_invocation", self.payload("PreInvocation", conv="c9")))
        self.assertEqual(len(t), 1)
        self.assertIn("Project memory is enabled", t[0])   # intro, not a stale align
        self.assertIn("use sqlite", t[0])
        self.assertEqual(len([e for e in self.events() if e["kind"] == "compaction"]), 1)

    def test_post_tool_use(self):
        run_hook("post_tool_use", self.payload(
            "PostToolUse", toolCall={"name": "write_file", "args": {"Path": "/w/a.py"}}, stepIdx=3))
        run_hook("post_tool_use", self.payload(
            "PostToolUse", toolCall={"name": "run_command", "args": {"CommandLine": "ls"}},
            error="exit status 1"))
        run_hook("post_tool_use", self.payload(
            "PostToolUse", toolCall={"name": "read_file", "args": {"Path": "/w/a.py"}}))
        ev = self.events()
        self.assertEqual([e["kind"] for e in ev], ["file_edit", "command"])
        self.assertEqual(ev[0]["data"]["path"], "/w/a.py")
        self.assertEqual(ev[1]["data"]["error"], "exit status 1")

    def test_bad_payload_never_breaks_agent(self):
        import subprocess
        import sys
        from helpers import PLUGIN
        p = subprocess.run([sys.executable, os.path.join(PLUGIN, "hooks", "pre_invocation.py")],
                           input="not json", capture_output=True, text=True)
        self.assertEqual(p.returncode, 0)
        self.assertEqual(p.stdout, "{}")

    def test_no_workspace_fallback(self):
        data = tempfile.mkdtemp()
        out = run_hook("session_start", {"hookEventName": "SessionStart", "conversationId": "z",
                                         "workspacePaths": [], "cwd": "/tmp/nowhere"},
                       env={"PLUGIN_DATA": data})
        self.assertTrue(self.texts(out))
        self.assertTrue(os.listdir(os.path.join(data, "projects")))


class PerfTest(unittest.TestCase):
    def test_incremental_under_300ms_on_50mb(self):
        ws = tempfile.mkdtemp()
        tp = os.path.join(tempfile.mkdtemp(), "transcript_full.jsonl")
        filler = "z" * 20000
        with open(tp, "w") as f:
            i = 0
            while f.tell() < 50 * 1024 * 1024:
                f.write(json.dumps({"step_index": i, "source": "MODEL", "type": "GENERIC",
                                    "content": filler}) + "\n")
                i += 1
        payload = {"hookEventName": "PreInvocation", "conversationId": "p",
                   "workspacePaths": [ws], "transcriptPath": tp, "modelName": "m"}
        t0 = time.time()
        run_hook("pre_invocation", payload)          # first catch-up over 50MB
        first = time.time() - t0
        write_transcript(tp, [model(i + 1, 1000, 100000)])
        t0 = time.time()
        run_hook("pre_invocation", payload)
        incr = time.time() - t0
        print(f"\n50MB catch-up {first*1000:.0f}ms, incremental {incr*1000:.0f}ms")
        self.assertLess(incr, 0.3)


if __name__ == "__main__":
    unittest.main()
