import sys, tempfile, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'swarmbrain'))
from mesh import Mesh, envelope, normalize, card_interface, parts_of

class ProtocolTests(unittest.TestCase):
 def test_v1(self):
  e=envelope('1.0','q','m',{'operation':'arrival'})
  self.assertEqual(e['method'],'SendMessage');self.assertNotIn('kind',e['params']['message'])
  self.assertEqual(e['params']['message']['role'],'ROLE_USER')
 def test_legacy(self):
  e=envelope('0.3','q','m','hello');self.assertEqual(e['method'],'message/send')
  self.assertEqual(e['params']['message']['parts'][0]['kind'],'text')
 def test_http200_rpcerror(self):
  r=normalize({'http_status':200,'response':{'jsonrpc':'2.0','id':'q','error':{'code':-32602}}},'q')
  self.assertEqual(r['state'],'protocol_error')
 def test_id_mismatch(self):
  self.assertEqual(normalize({'http_status':200,'response':{'jsonrpc':'2.0','id':'other','result':{}}},'q')['state'],'invalid_protocol_response')
 def test_pending_not_complete(self):
  r=normalize({'http_status':200,'response':{'jsonrpc':'2.0','id':'q','result':{'task':{'id':'t','status':{'state':'TASK_STATE_WORKING'}}}}},'q')
  self.assertEqual(r['state'],'pending')
 def test_input_required(self):
  r=normalize({'http_status':200,'response':{'jsonrpc':'2.0','id':'q','result':{'id':'t','status':{'state':'input-required'}}}},'q')
  self.assertEqual(r['state'],'input_required')
 def test_direct_message(self):
  r=normalize({'http_status':200,'response':{'jsonrpc':'2.0','id':'q','result':{'message':{'parts':[{'data':{'value':1}}]}}}},'q')
  self.assertEqual(r['state'],'response_received')
 def test_registry_persists(self):
  with tempfile.TemporaryDirectory() as d:
   m=Mesh(d);p=m.register('peer','https://example.com/.well-known/agent-card.json')
   other=Mesh(d);self.assertEqual(other.state['peers']['peer']['node_id'],p['node_id'])
   self.assertEqual(other.register('alias','https://example.com/.well-known/agent-card.json')['id'],'peer')
 def test_no_random_routing(self):
  with tempfile.TemporaryDirectory() as d:self.assertEqual(Mesh(d).route('anything'),[])
 def test_parts_nested(self):self.assertEqual(parts_of({'message':{'parts':[{'text':'x'}]}}),[{'text':'x'}])

if __name__=='__main__':unittest.main()
