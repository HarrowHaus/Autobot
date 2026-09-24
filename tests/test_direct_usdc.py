"""Public collector regression tests use complete synthetic chain evidence."""
import json, tempfile, unittest
from pathlib import Path
from swarmbrain.direct_usdc import create_quote, scan_orders, allocate_amount, format_usdc
from test_payment_recovery import RPC, transfer, PAY

class DirectUSDC(unittest.TestCase):
    def q(self,td,k='o1',**kw):
        return create_quote(orders_dir=td,order_id=k,query='verification',requester='test-fixture',comment_id=1,issue_number=33,pay_to=PAY,rpc_fn=RPC(100),**kw)
    def test_quote_is_persisted_and_unique(self):
        with tempfile.TemporaryDirectory() as td:
            a=self.q(td);b=self.q(td,'o2')
            self.assertNotEqual(a['amount_atomic'],b['amount_atomic'])
            self.assertEqual(self.q(td),a)
    def test_exact_confirmed_transfer_fulfills_once(self):
        with tempfile.TemporaryDirectory() as td:
            q=self.q(td);rpc=RPC(120,[transfer(q['amount_atomic'],110)])
            for expected in (1,0):
                out=scan_orders(td,PAY,rpc,lambda *_:[{'peer':'test'}])
                self.assertEqual(len(out['fulfilled']),expected)
    def test_wrong_amount_does_not_fulfill(self):
        with tempfile.TemporaryDirectory() as td:
            q=self.q(td)
            out=scan_orders(td,PAY,RPC(120,[transfer(q['amount_atomic']+1,110)]),lambda *_:[{'peer':'test'}])
            self.assertEqual(out['fulfilled'],[])
    def test_expired_amount_is_never_reused(self):
        used=allocate_amount('o1',[])
        self.assertNotEqual(allocate_amount('o1',[(None,{'status':'expired','amount_atomic':used})]),used)
    def test_id_cannot_escape_storage(self):
        with tempfile.TemporaryDirectory() as td:
            for key in ('../oops','/tmp/oops','.hidden'):
                with self.assertRaises(ValueError):self.q(td,key)
    def test_format_is_integer_exact(self):
        self.assertEqual(format_usdc(10001),'0.010001')
    def test_changed_replay_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            self.q(td)
            with self.assertRaises(ValueError):
                create_quote(orders_dir=td,order_id='o1',query='DIFFERENT',requester='test-fixture',comment_id=1,issue_number=33,pay_to=PAY,rpc_fn=RPC())
if __name__=='__main__':unittest.main()
