import json
import multiprocessing
import os
import tempfile
import unittest

import helpers  # noqa: F401  (sets sys.path)

from agymem import brief as B
from agymem import config as C
from agymem import ledger as L
from agymem.store import Store, redact, resolve_root


def _writer(root, n, tag):
    s = Store(root)
    for i in range(n):
        s.append("events.jsonl", {"tag": tag, "i": i, "pad": "x" * 500})


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.ws = tempfile.mkdtemp()

    def test_resolve_root(self):
        self.assertEqual(resolve_root({"workspacePaths": [self.ws, "/b"]}),
                         os.path.join(self.ws, ".agy-memory"))
        os.environ.pop("PLUGIN_DATA", None)
        r = resolve_root({"workspacePaths": [], "cwd": "/tmp/x"})
        self.assertTrue(r.startswith(os.path.expanduser("~/.agy-memory/projects/")))
        os.environ["PLUGIN_DATA"] = self.ws
        try:
            self.assertTrue(resolve_root({"cwd": "/tmp/x"}).startswith(self.ws))
        finally:
            os.environ.pop("PLUGIN_DATA")

    def test_ensure_creates_self_gitignore(self):
        s = Store(os.path.join(self.ws, ".agy-memory")).ensure()
        with open(s.path(".gitignore")) as f:
            self.assertIn("*", f.read().splitlines())
        self.assertFalse(os.path.exists(os.path.join(self.ws, ".gitignore")))

    def test_redaction(self):
        pats = C.DEFAULTS["redactPatterns"]
        out = redact({"cmd": "export API_KEY=abc123 && run", "k": ["sk-" + "a" * 20]}, pats)
        self.assertEqual(out["cmd"], "export API_KEY=[REDACTED] && run")
        self.assertEqual(out["k"], ["[REDACTED]"])

    def test_redacted_jsonl_stays_valid(self):
        s = Store(os.path.join(self.ws, "m"), C.DEFAULTS["redactPatterns"]).ensure()
        s.append("e.jsonl", {"t": 'password: "hunter2"}'})
        self.assertEqual(len(s.read("e.jsonl")), 1)

    def test_concurrent_append(self):
        root = os.path.join(self.ws, "m")
        Store(root).ensure()
        procs = [multiprocessing.Process(target=_writer, args=(root, 200, t)) for t in range(4)]
        for p in procs:
            p.start()
        for p in procs:
            p.join()
        rows = Store(root).read("events.jsonl")
        self.assertEqual(len(rows), 800)
        with open(os.path.join(root, "events.jsonl")) as f:
            for line in f:
                json.loads(line)

    def test_config_merge(self):
        root = os.path.join(self.ws, "m")
        Store(root).ensure()
        with open(os.path.join(root, "config.json"), "w") as f:
            json.dump({"briefMaxTokens": 10, "bogus": 1}, f)
        cfg = C.load(root)
        self.assertEqual(cfg["briefMaxTokens"], 10)
        self.assertNotIn("bogus", cfg)


class LedgerBriefTest(unittest.TestCase):
    def test_supersede_and_status(self):
        a = L.new_entry("constraint", "do not touch src/legacy", "c1")
        b = L.new_entry("constraint", "do not touch src/legacy or src/vendor", "c1",
                        supersedes=a["id"])
        p = L.new_entry("progress", "M1 done", "c1")
        d = L.status_update(p, "done", "c1")
        view = L.current_view([a, b, p, d])
        self.assertEqual([e["id"] for e in view], [b["id"], d["id"]])
        self.assertEqual([e["id"] for e in L.history([a, b], b["id"])], [a["id"], b["id"]])

    def test_brief_scoping(self):
        es = [L.new_entry("constraint", "不要修改 src/", "c1"),
              L.new_entry("progress", "mine: step 3", "c2"),
              L.new_entry("progress", "other: half done", "c1"),
              L.new_entry("fact", "key REG_03", "c1", source=["c1#40"])]
        out = B.render(es, "c2")
        self.assertIn("不要修改 src/", out)
        self.assertIn("mine: step 3", out)
        self.assertNotIn("other: half done\n", out)
        self.assertIn("c1:", out)            # other-session pointer line
        self.assertIn("src: c1#40", out)

    def test_brief_truncation_priority(self):
        es = [L.new_entry("constraint", f"constraint {i} " + "x" * 40, "c") for i in range(5)]
        es += [L.new_entry("fact", f"fact {i} " + "y" * 40, "c") for i in range(50)]
        out = B.render(es, "c", max_tokens=200)
        self.assertLessEqual(B.est_tokens(out), 230)
        self.assertEqual(out.count("constraint "), 5)
        self.assertIn("truncated", out)

    def test_empty_brief(self):
        self.assertEqual(B.render([], "c"), "")

    def test_est_tokens_cjk(self):
        self.assertEqual(B.est_tokens("压缩记忆"), 4)
        self.assertEqual(B.est_tokens("abcdefgh"), 2)


if __name__ == "__main__":
    unittest.main()
