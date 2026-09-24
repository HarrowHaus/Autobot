import json, tempfile, unittest
from pathlib import Path
from swarmbrain.direct_usdc import create_quote, scan_orders, transfer_logs, USDC, TRANSFER_TOPIC

PAY="0x"+"ab"*20
class FakeRPC:
    def __init__(self,latest=100,logs=None):self.latest=latest;self.logs=logs or [];self.calls=[]
    def __call__(self,method,params):
        self.calls.append((method,params))
        if method=="eth_blockNumber":return hex(self.latest)
        if method=="eth_getLogs":return self.logs
        raise AssertionError(method)
class DirectUSDC(unittest.TestCase):
    def test_quote_is_persisted_and_unique(self):
        with tempfile.TemporaryDirectory() as td:
            rpc=FakeRPC()
            a=create_quote(orders_dir=td,order_id="o1",query="verification",requester="u",comment_id=1,issue_number=19,pay_to=PAY,rpc_fn=rpc)
            b=create_quote(orders_dir=td,order_id="o2",query="research",requester="u",comment_id=2,issue_number=19,pay_to=PAY,rpc_fn=rpc)
            self.assertNotEqual(a["amount_atomic"],b["amount_atomic"])
            self.assertEqual(a["status"],"awaiting_payment")
            self.assertTrue(a["quote_hash"])
    def test_exact_confirmed_transfer_fulfills_once(self):
        with tempfile.TemporaryDirectory() as td:
            quote=create_quote(orders_dir=td,order_id="o1",query="verification",requester="u",comment_id=1,issue_number=19,pay_to=PAY,rpc_fn=FakeRPC(100))
            tx="0x"+"11"*32
            log={"transactionHash":tx,"blockNumber":hex(110),"logIndex":"0x0","data":hex(quote["amount_atomic"])}
            rpc=FakeRPC(120,[log])
            out=scan_orders(td,PAY,rpc_fn=rpc,route_fn=lambda q,l:[{"peer":"peer-a","query":q}])
            self.assertEqual(len(out["fulfilled"]),1)
            saved=json.loads((Path(td)/"o1.json").read_text())
            self.assertEqual(saved["status"],"fulfilled")
            self.assertEqual(saved["settlement"]["transaction"],tx)
            out2=scan_orders(td,PAY,rpc_fn=rpc,route_fn=lambda q,l:[])
            self.assertEqual(out2["fulfilled"],[])
    def test_wrong_amount_does_not_fulfill(self):
        with tempfile.TemporaryDirectory() as td:
            quote=create_quote(orders_dir=td,order_id="o1",query="verification",requester="u",comment_id=1,issue_number=19,pay_to=PAY,rpc_fn=FakeRPC(100))
            log={"transactionHash":"0x"+"22"*32,"blockNumber":hex(110),"logIndex":"0x0","data":hex(quote["amount_atomic"]+1)}
            out=scan_orders(td,PAY,rpc_fn=FakeRPC(120,[log]),route_fn=lambda q,l:[])
            self.assertEqual(out["fulfilled"],[])
if __name__=="__main__":unittest.main()
