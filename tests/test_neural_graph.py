import json, tempfile, unittest
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"swarmbrain"))
from neural_graph import AgentGraph, ROOK_ID, stable_agent_id

class AgentGraphTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        (self.root/"data").mkdir()
        (self.root/"reports").mkdir()
        self.g=AgentGraph(self.root)
    def tearDown(self): self.tmp.cleanup()

    def test_stable_identity(self):
        self.assertEqual(stable_agent_id("x","Y"),stable_agent_id("X","y"))

    def test_catalog_mesh_merge_on_same_card(self):
        card="https://example.com/.well-known/agent-card.json"
        self.g.seed_catalog({"records":[{"catalog_id":"c1","name":"Example","card_url":card,"source":"test"}]})
        self.g.seed_mesh({"peers":{"ex":{"name":"Example Mesh","card_url":card,"endpoint":"https://example.com/a2a","status":"connected","calls":2,"responses":2,"verified_results":1,"capabilities":[]}}})
        ids=[a for a in self.g.ledger["agents"] if a!=ROOK_ID]
        self.assertEqual(len(ids),1)
        a=self.g.ledger["agents"][ids[0]]
        self.assertEqual(a["mesh_alias"],"ex")
        self.assertEqual(a["status"],"connected")

    def test_every_event_append_only_and_deduped(self):
        a=self.g.ensure_agent("test","a",name="A")
        e={"event_id":"e1","source_agent":ROOK_ID,"target_agent":a,"event_type":"conversation","observed_at":"2026-01-01T00:00:00Z"}
        self.assertTrue(self.g.record_event(e))
        self.assertFalse(self.g.record_event(e))
        lines=(self.root/"reports/agent-interactions.ndjson").read_text().strip().splitlines()
        self.assertEqual(len(lines),1)

    def test_validated_result_strengthens_more(self):
        a=self.g.ensure_agent("test","a",name="A")
        self.g.record_event({"event_id":"e1","source_agent":a,"target_agent":ROOK_ID,"event_type":"conversation","observed_at":"2026-01-01T00:00:00Z"})
        self.g.record_event({"event_id":"e2","source_agent":a,"target_agent":ROOK_ID,"event_type":"result_validated","observed_at":"2026-01-01T00:00:01Z"})
        edges=list(self.g.synapses["edges"].values())
        weights={e["relation"]:e["weight"] for e in edges}
        self.assertGreater(weights["result_validated"],weights["conversation"])
        self.assertEqual(self.g.ledger["agents"][a]["validated_result_count"],1)

    def test_referral_updates_both_agents(self):
        a=self.g.ensure_agent("test","a",name="A")
        b=self.g.ensure_agent("test","b",name="B")
        self.g.record_event({"event_id":"r1","source_agent":a,"target_agent":b,"event_type":"referral","observed_at":"2026-01-01T00:00:00Z"})
        self.assertEqual(self.g.ledger["agents"][a]["referrals_given"],1)
        self.assertEqual(self.g.ledger["agents"][b]["referrals_received"],1)

    def test_public_lane_is_not_claimed_independent_owner(self):
        a=self.g.add_public_lane("SharedAccount","Instinct",app_slug=None)
        n=self.g.ledger["agents"][a]
        self.assertIn("self-reported-lane-under-shared-account",n["provenance"])
        self.assertEqual(n["accounts"][0]["handle"],"SharedAccount")

    def test_summary_counts(self):
        a=self.g.ensure_agent("test","a",name="A")
        self.g.record_event({"event_id":"e1","source_agent":ROOK_ID,"target_agent":a,"event_type":"conversation","observed_at":"2026-01-01T00:00:00Z"})
        s=self.g.summary()
        self.assertEqual(s["agent_count"],2)
        self.assertEqual(s["interaction_events"],1)

if __name__=="__main__": unittest.main()
