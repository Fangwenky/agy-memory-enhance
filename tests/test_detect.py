import os
import tempfile
import unittest

from helpers import checkpoint, model, tool, user, write_transcript

from agymem import config as C
from agymem import detect as D
from agymem import transcript as T


class TranscriptTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.path = os.path.join(self.dir, "transcript_full.jsonl")

    def test_incremental_and_partial_line(self):
        write_transcript(self.path, [user(0, "hi"), model(1, 100)])
        steps, off, reset = T.read_new(self.path, 0)
        self.assertEqual([s["step_index"] for s in steps], [0, 1])
        self.assertFalse(reset)
        with open(self.path, "a") as f:
            f.write('{"step_index": 2, "type": "GEN')  # half-written line
        steps, off2, _ = T.read_new(self.path, off)
        self.assertEqual(steps, [])
        self.assertEqual(off2, off)
        with open(self.path, "a") as f:
            f.write('ERIC"}\n')
        steps, _, _ = T.read_new(self.path, off2)
        self.assertEqual(steps[0]["step_index"], 2)

    def test_reset_when_file_shrinks(self):
        write_transcript(self.path, [user(0, "a"), model(1, 1), tool(2)])
        _, off, _ = T.read_new(self.path, 0)
        write_transcript(self.path, [user(0, "b")], mode="w")
        steps, _, reset = T.read_new(self.path, off)
        self.assertTrue(reset)
        self.assertEqual(T.user_text(steps[0]), "b")

    def test_missing_file(self):
        self.assertEqual(T.read_new(None, 0), ([], 0, False))
        self.assertEqual(T.read_new("/nope/x.jsonl", 5), ([], 5, False))

    def test_ctx_tokens_sums_cache(self):
        self.assertEqual(T.ctx_tokens(model(1, 636, 56325)), 56961)
        self.assertIsNone(T.ctx_tokens(tool(2)))

    def test_find_step(self):
        write_transcript(self.path, [user(0, "a"), model(1, 1), user(12, "z")])
        self.assertEqual(T.user_text(T.find_step(self.path, 12)), "z")
        self.assertIsNone(T.find_step(self.path, 3))


class DetectTest(unittest.TestCase):
    cfg = dict(C.DEFAULTS)

    def scan(self, state, steps):
        return D.scan(state, steps, self.cfg, "c")

    def test_checkpoint_is_primary_signal(self):
        st = D.fresh_state()
        ev, peaks = self.scan(st, [model(1, 1000, 517000), tool(2), checkpoint(3, 513000),
                                   model(4, 30000, 2000)])
        kinds = [k for k, _, _ in ev]
        self.assertEqual(kinds.count("compaction"), 1)   # no double count from the token drop
        self.assertEqual(peaks, [518000])
        self.assertEqual(st["pendingAlign"], "checkpoint")
        self.assertEqual(st["peak"], 32000)
        self.assertIn("summary", ev[0][2])

    def test_token_drop_fallback(self):
        st = D.fresh_state()
        ev, peaks = self.scan(st, [model(1, 1000, 200000), model(2, 30000, 0)])
        self.assertEqual([d["signal"] for k, _, d in ev if k == "compaction"], ["token_drop"])
        self.assertEqual(peaks, [201000])

    def test_small_peak_drop_is_not_compaction(self):
        # M0 false positive: 42,976 -> 27,857 after a model switch
        st = D.fresh_state()
        ev, _ = self.scan(st, [model(1, 42976), model(2, 27857)])
        self.assertFalse([e for e in ev if e[0] == "compaction"])

    def test_cache_miss_is_not_compaction(self):
        st = D.fresh_state()
        ev, _ = self.scan(st, [model(1, 600, 150000), model(2, 151000, 0)])
        self.assertFalse([e for e in ev if e[0] == "compaction"])

    def test_second_compaction_detected(self):
        st = D.fresh_state()
        steps = [model(1, 0, 300000), checkpoint(2, 300000), model(3, 30000),
                 model(4, 0, 290000), checkpoint(5, 290000), model(6, 31000)]
        ev, peaks = self.scan(st, steps)
        self.assertEqual(peaks, [300000, 290000])
        self.assertEqual(st["compactions"], 2)

    def test_user_input_events(self):
        ev, _ = self.scan(D.fresh_state(), [user(0, "不要改 src/")])
        self.assertEqual(ev, [("user_input", 0, {"text": "不要改 src/"})])

    def test_nudge_levels_and_ledger_suppression(self):
        st = D.fresh_state()
        peak = 400000  # learned: soft limit = 300k
        st["lastCtx"] = 290000
        self.assertIsNone(D.should_nudge(st, self.cfg, peak))
        st["lastCtx"] = 305000
        self.assertIsNotNone(D.should_nudge(st, self.cfg, peak))
        st["lastCtx"] = 320000          # < 30k since last nudge
        self.assertIsNone(D.should_nudge(st, self.cfg, peak))
        st["lastCtx"] = 336000
        D.observe_ledger(st, 123)       # agent saved memory at 336k
        self.assertIsNone(D.should_nudge(st, self.cfg, peak))
        st["lastCtx"] = 367000
        self.assertIsNotNone(D.should_nudge(st, self.cfg, peak))

    def test_default_soft_limit_without_model_data(self):
        st = D.fresh_state()
        st["lastCtx"] = 149000
        self.assertIsNone(D.should_nudge(st, self.cfg, None))
        st["lastCtx"] = 151000
        self.assertEqual(D.should_nudge(st, self.cfg, None)["limit"], 150000)
        # unknown threshold -> geometric spacing: next nudge needs +50% (~226k)
        st["lastCtx"] = 200000
        self.assertIsNone(D.should_nudge(st, self.cfg, None))
        st["lastCtx"] = 227000
        self.assertIsNotNone(D.should_nudge(st, self.cfg, None))

    def test_compaction_resets_nudge_marks(self):
        st = D.fresh_state()
        st.update(lastNudgeCtx=300000, ledgerCtx=310000, peak=320000)
        self.scan(st, [checkpoint(9, 320000)])
        self.assertIsNone(st["lastNudgeCtx"])
        self.assertIsNone(st["ledgerCtx"])


if __name__ == "__main__":
    unittest.main()
