import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'swarmbrain'))
from mesh import Mesh, write_json
from groups import GroupNetwork, decoded_answer

class ReplyTransport:
    def __init__(self):self.calls=[]
    def call(self,url,body=None,headers=None):
        self.calls.append((url,body))
        return {'http_status':200,'latency_ms':1,'response':{'jsonrpc':'2.0','id':body['id'],
                'result':{'kind':'message','parts':[{'kind':'text','text':'Unit-test response; not live evidence.'}]}}}

class GroupTests(unittest.TestCase):
    def setUp(self):
        self.dir=tempfile.TemporaryDirectory();self.root=Path(self.dir.name)
        self.transport=ReplyTransport();self.mesh=Mesh(self.root,network=self.transport)
        for a in ['x','y','z']:
            p=self.mesh.register(a,f'https://{a}.example/.well-known/agent-card.json')
            p.update(status='connected',endpoint=f'https://{a}.example/a2a',protocol_version='0.3',group_adapter='public_text_question')
        self.mesh.save();self.g=GroupNetwork(self.root,self.mesh)
        self.g.define('sources','Sources',['x','y'])
        self.g.define('counterexamples','Counterexamples',['y','z'])
        self.g.define('swarm','Swarm',['sources','counterexamples'])
    def tearDown(self):self.dir.cleanup()
    def test_shared_peer_called_once(self):
        r=self.g.ask('swarm','Public test question','q1')
        self.assertEqual(len(self.transport.calls),3)
        self.assertEqual(len(r['contributions']['y']['paths']),2)
        self.assertIn('y',r['children']['sources']['contributor_refs'])
        self.assertIn('y',r['children']['counterexamples']['contributor_refs'])
    def test_no_fake_consensus(self):
        r=self.g.ask('swarm','question','q1')
        self.assertEqual(r['aggregation'],'attributed_collection_not_consensus')
        self.assertEqual(r['verified_answers'],0)
    def test_cycle_rollback(self):
        with self.assertRaises(ValueError):self.g.define('sources','broken',['swarm'])
        self.assertEqual(self.g.state['groups']['sources']['children'],['x','y'])
    def test_unknown_child(self):
        with self.assertRaises(ValueError):self.g.define('unknown','bad',['absent'])
    def test_duplicate_children(self):
        self.g.define('dup','Dup',['x','x']);self.assertEqual(self.g.plan('dup')['unique_peers'],1)
    def test_request_replay(self):
        a=self.g.ask('swarm','question','q1');b=self.g.ask('swarm','question','q1')
        self.assertEqual(a,b);self.assertEqual(len(self.transport.calls),3)
    def test_changed_request_id(self):
        self.g.ask('swarm','one','q1')
        with self.assertRaises(ValueError):self.g.ask('swarm','two','q1')
    def test_budget(self):
        r=self.g.ask('swarm','question','q1',max_peers=2)
        self.assertEqual(len(self.transport.calls),2);self.assertEqual(r['state'],'partial')
        self.assertEqual(r['skipped']['z'],'per_question_peer_budget')
    def test_unavailable(self):
        self.mesh.state['peers']['z']['status']='paused'
        r=self.g.ask('swarm','question','q1')
        self.assertEqual(len(self.transport.calls),2);self.assertEqual(r['skipped']['z'],'paused')
    def test_no_adapter(self):
        self.mesh.state['peers']['x'].pop('group_adapter')
        r=self.g.ask('swarm','question','q1');self.assertEqual(r['skipped']['x'],'no_question_adapter')
    def test_persistence(self):
        prior=self.g.state['groups']['swarm']['node_id'];g=GroupNetwork(self.root)
        self.assertEqual(g.state['groups']['swarm']['node_id'],prior)
        self.assertEqual(g.plan('swarm')['unique_peers'],3)
    def test_name_collision(self):
        with self.assertRaises(ValueError):self.g.define('x','bad',['y'])
    def test_invalid_budget(self):
        with self.assertRaises(ValueError):self.g.ask('swarm','question','q1',max_peers=100)
    def test_empty_question(self):
        with self.assertRaises(ValueError):self.g.ask('swarm','','q1')
    def test_export(self):
        r=self.g.export();self.assertEqual(len(r['groups']),3);self.assertEqual(len(r['edges']),6)
    def test_hash_id_stable(self):
        self.g.ask('swarm','question','q1')
        for tid in self.mesh.state['tasks']:self.assertTrue(tid.startswith('g-'))
    def test_application_error_not_answer(self):
        out=decoded_answer('{"error":"429 RESOURCE_EXHAUSTED"}')
        self.assertEqual(out['answer_text'],'');self.assertIn('429',out['application_error'])
    def test_provider_envelope_decoded(self):
        out=decoded_answer('{"structured":{"answer":"specific answer"},"model":"reported-model"}')
        self.assertEqual(out['answer_text'],'specific answer')
        self.assertEqual(out['provider_report']['model'],'reported-model')
    def test_bad_synthesis_type(self):
        with self.assertRaises(ValueError):self.g.ask('swarm','question','q1',synthesize='false')
    def test_bad_group_job_cannot_dispatch(self):
        with self.assertRaises(ValueError):self.g.ask('missing','question','q1')
        self.assertEqual(len(self.transport.calls),0)

if __name__=='__main__':unittest.main()
