import gzip
import io
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

from helpers import PLUGIN, model, run_hook, tool, user, write_transcript

from agymem import brief as B
from agymem import cli
from agymem.store import Store

MEM = os.path.join(PLUGIN, "skills", "agy-memory", "scripts", "mem")


class Base(unittest.TestCase):
    def setUp(self):
        self.ws = tempfile.mkdtemp()
        self.root = os.path.join(self.ws, ".agy-memory")
        self.tp = os.path.join(tempfile.mkdtemp(), "transcript_full.jsonl")
        open(self.tp, "w").close()

    def mem(self, *args, conv="c1"):
        buf = io.StringIO()
        with redirect_stdout(buf):
            try:
                cli.main(["--root", self.root, "--conv", conv, *args])
            except SystemExit as e:
                if e.code not in (0, None):
                    raise AssertionError(f"mem exited {e.code}: {buf.getvalue()}")
        return buf.getvalue()

    def payload(self, event, conv="c1", **kw):
        return {"hookEventName": event, "conversationId": conv, "workspacePaths": [self.ws],
                "transcriptPath": self.tp, "cwd": self.ws, "modelName": "m", **kw}


class CliTest(Base):
    def test_add_show_supersede_done(self):
        out = self.mem("add", "constraint", "do", "not", "touch", "src/legacy")
        cid = out.split("[")[1].split("]")[0]
        self.mem("add", "progress", "step 1 done")
        self.assertIn("do not touch src/legacy", self.mem("show", "constraint"))
        self.mem("supersede", cid, "do not touch src/legacy or src/vendor")
        shown = self.mem("show", "constraint")
        self.assertIn("src/vendor", shown)
        self.assertEqual(shown.count("\n"), 1)
        self.assertIn("do not touch src/legacy\n", self.mem("show", cid))   # history kept
        pid = self.mem("show", "progress").split("[")[1].split("]")[0]
        self.mem("done", pid)
        self.assertEqual(self.mem("show", "progress").strip(), "(none)")
        self.assertIn("done", self.mem("show", "progress", "--all-status"))

    def test_brief_scoped_to_conv(self):
        self.mem("add", "constraint", "全局约束")
        self.mem("add", "progress", "c1 进度", conv="c1")
        self.mem("add", "progress", "c2 进度", conv="c2")
        b = self.mem("brief", conv="c2")
        self.assertIn("全局约束", b)
        self.assertIn("c2 进度", b)
        self.assertNotIn("c1 进度\n", b)
        self.assertIn("c1:", b)

    def test_current_conv_from_hooks(self):
        run_hook("session_start", self.payload("SessionStart", conv="live"))
        buf = io.StringIO()
        with redirect_stdout(buf):
            cli.main(["--root", self.root, "add", "progress", "x"])
        self.assertEqual(Store(self.root).read("ledger.jsonl")[0]["convId"], "live")

    def test_show_pointer_from_transcript_and_archive(self):
        write_transcript(self.tp, [user(0, "原始指令：用 REG_07_abc123"), model(1, 10), tool(2)])
        run_hook("pre_invocation", self.payload("PreInvocation"))
        self.assertIn("REG_07_abc123", self.mem("show", "c1#0"))
        run_hook("stop", self.payload("Stop", terminationReason="NO_TOOL_CALL",
                                      continuationActive=False))
        os.remove(self.tp)                               # transcript gone -> archive
        self.assertIn("REG_07_abc123", self.mem("show", "c1#0"))

    def test_search_ledger_events_archive(self):
        write_transcript(self.tp, [user(0, "please never use eval()"), model(1, 10),
                                   {"step_index": 2, "type": "GENERIC", "content": "zebra-42 output"}])
        run_hook("pre_invocation", self.payload("PreInvocation"))
        run_hook("stop", self.payload("Stop", terminationReason="NO_TOOL_CALL",
                                      continuationActive=False))
        self.mem("add", "decision", "chose zebra-42 because fast")
        self.assertIn("event user_input @ c1#0", self.mem("search", "never", "eval"))
        out = self.mem("search", "zebra-42")
        self.assertIn("ledger", out)
        self.assertIn("transcript c1#2", out)
        self.assertIn("(0 hits)", self.mem("search", "zebra-42", "--where", "ledger", "--type", "fact"))

    def test_timeline_file_filter(self):
        run_hook("post_tool_use", self.payload(
            "PostToolUse", toolCall={"name": "edit_file", "args": {"Path": "/w/core.py"}}, stepIdx=5))
        run_hook("post_tool_use", self.payload(
            "PostToolUse", toolCall={"name": "write_file", "args": {"Path": "/w/other.py"}}))
        self.mem("add", "decision", "core.py keeps sync API")
        out = self.mem("timeline", "--file", "core.py")
        self.assertIn("edit_file /w/core.py", out)
        self.assertIn("keeps sync API", out)
        self.assertNotIn("other.py", out)

    def test_session_list_and_index(self):
        write_transcript(self.tp, [user(0, "重构解析器"), model(1, 10)])
        run_hook("pre_invocation", self.payload("PreInvocation"))
        run_hook("post_tool_use", self.payload(
            "PostToolUse", toolCall={"name": "write_file", "args": {"Path": "/w/p.py"}}))
        run_hook("stop", self.payload("Stop", terminationReason="NO_TOOL_CALL",
                                      continuationActive=False))
        self.assertIn("重构解析器", self.mem("session"))
        idx = self.mem("session", "c1")
        self.assertIn("/w/p.py", idx)
        self.assertIn("## First request", idx)

    def test_shim_end_to_end(self):
        run_hook("session_start", self.payload("SessionStart"))
        shim = os.path.join(self.root, "bin", "mem")
        p = subprocess.run([shim, "add", "fact", "port is 8443", "--source", "file:cfg.yml"],
                           capture_output=True, text=True)
        self.assertEqual(p.returncode, 0, p.stderr)
        p = subprocess.run([shim, "brief"], capture_output=True, text=True)
        self.assertIn("port is 8443 (src: file:cfg.yml)", p.stdout)

    def test_doctor(self):
        run_hook("session_start", self.payload("SessionStart"))
        write_transcript(self.tp, [user(0, "x")])
        run_hook("pre_invocation", self.payload("PreInvocation"))
        p = subprocess.run([sys.executable, MEM, "--root", self.root, "doctor"],
                           capture_output=True, text=True)
        self.assertIn("[ok] hooks have run", p.stdout)
        self.assertIn("[ok] transcript readable", p.stdout)


class StopTest(Base):
    def stop(self, **kw):
        kw.setdefault("terminationReason", "NO_TOOL_CALL")
        kw.setdefault("continuationActive", False)
        return run_hook("stop", self.payload("Stop", **kw))

    def edits(self, n):
        for i in range(n):
            run_hook("post_tool_use", self.payload(
                "PostToolUse", toolCall={"name": "write_file", "args": {"Path": f"/w/f{i}.py"}}))

    def test_archive_is_incremental_multi_member(self):
        write_transcript(self.tp, [user(0, "a"), model(1, 1)])
        self.stop()
        write_transcript(self.tp, [tool(2)])
        self.stop()
        self.stop()                                     # nothing new: no empty member
        arc = os.path.join(self.root, "archive", "c1.jsonl.gz")
        with gzip.open(arc, "rt") as f:
            self.assertEqual(len(f.read().splitlines()), 3)
        with open(self.tp, "rb") as a, gzip.open(arc, "rb") as b:
            self.assertEqual(a.read(), b.read())

    def test_turn_end_event_with_git(self):
        subprocess.run(["git", "init", "-q", self.ws])
        open(os.path.join(self.ws, "new.txt"), "w").close()
        self.stop()
        ev = [e for e in Store(self.root).read("events.jsonl") if e["kind"] == "turn_end"][0]
        self.assertIn("new.txt", ev["data"]["gitChanged"])

    def test_nudge_truth_table(self):
        self.edits(4)
        self.assertEqual(self.stop(), {})                       # below threshold
        self.edits(1)
        self.assertEqual(self.stop(continuationActive=True), {})  # already continuing
        self.assertEqual(self.stop(terminationReason="USER_CANCELED"), {})
        out = self.stop()
        self.assertEqual(out["decision"], "continue")
        self.assertIn("5 file edits", out["reason"])
        self.assertEqual(self.stop(continuationActive=True), {})  # once per turn

    def test_ledger_write_resets_edit_counter(self):
        self.edits(6)
        self.mem("add", "progress", "saved")
        self.assertEqual(self.stop(), {})

    def test_nudge_can_be_disabled(self):
        os.makedirs(self.root, exist_ok=True)
        with open(os.path.join(self.root, "config.json"), "w") as f:
            f.write('{"stopNudge": false}')
        self.edits(6)
        self.assertEqual(self.stop(), {})


class RuleTest(unittest.TestCase):
    def test_rule_is_short(self):
        with open(os.path.join(PLUGIN, "rules", "AGENTS.md"), encoding="utf-8") as f:
            self.assertLess(B.est_tokens(f.read()), 400)


if __name__ == "__main__":
    unittest.main()
