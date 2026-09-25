import copy
import json
import tempfile
import unittest
from pathlib import Path
from swarmbrain.payment_recovery import (scan_orders, digest, atomic_write, verified_hit, TOKEN, TOPIC)

PAY = '0x'+'ab'*20
PAYER = '0x'+'cd'*20

def bh(n): return '0x'+f'{n:064x}'

def quote(order_id='o1', amount=10001):
    out = dict(schema_version=1, order_id=order_id, issue_number=33, comment_id=1,
        requester='test-fixture-only', service='read_only_route_selection', query='verification', limit=3,
        network='eip155:8453', chain_id=8453, asset='USDC', token_contract=TOKEN, pay_to=PAY,
        amount_atomic=amount, amount_usdc=f'{amount/1000000:.6f}', from_block=100,
        expires_after_block=200, confirmations=5, status='awaiting_payment', created_at='2026-09-24T00:00:00Z')
    out['quote_hash'] = digest(out)
    return out

def transfer(amount=10001, block=180, index=0, tx='0x'+'11'*32):
    return dict(address=TOKEN, topics=[TOPIC, '0x'+'0'*24+PAYER[2:], '0x'+'0'*24+PAY[2:]],
                data=hex(amount), blockNumber=hex(block), blockHash=bh(block), transactionHash=tx,
                logIndex=hex(index), removed=False)

class RPC:
    def __init__(self, latest=300, logs=None):
        self.latest, self.logs, self.calls = latest, logs or [], []
        self.chain = 8453
        self.fail_logs = False
        self.receipt_status = '0x1'
        self.canonical_override = {}
    def __call__(self, method, params):
        self.calls.append((method, params))
        if method == 'eth_chainId': return hex(self.chain)
        if method == 'eth_blockNumber': return hex(self.latest)
        if method == 'eth_getLogs':
            if self.fail_logs: raise TimeoutError()
            return [copy.deepcopy(x) for x in self.logs if int(params[0]['fromBlock'],16) <= int(x['blockNumber'],16) <= int(params[0]['toBlock'],16)]
        if method == 'eth_getTransactionReceipt':
            logs = [x for x in self.logs if x['transactionHash'] == params[0]]
            return dict(status=self.receipt_status, transactionHash=params[0], blockHash=logs[0]['blockHash'], blockNumber=logs[0]['blockNumber'], logs=logs)
        if method == 'eth_getBlockByNumber':
            n=int(params[0],16)
            return {'hash': self.canonical_override.get(n, bh(n))}
        raise AssertionError(method)

class RecoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.save(quote())
    def tearDown(self): self.tmp.cleanup()
    def save(self,o): atomic_write(self.root/(o['order_id']+'.json'),o)
    def saved(self,k='o1'): return json.loads((self.root/(k+'.json')).read_text())
    def scan(self,rpc=None, route=None, **kw):
        return scan_orders(self.root,PAY,rpc or RPC(),route_fn=route, **kw)

    def test_delayed_watcher_recovers_payment_made_on_time(self):
        result=self.scan(RPC(300,[transfer()]),lambda *_:[{'peer':'test'}])
        self.assertEqual(self.saved()['status'],'fulfilled')
        self.assertTrue(self.saved()['payment_recovered_after_expiry'])
        self.assertEqual(len(result['fulfilled']),1)

    def test_previously_expired_quote_is_reconciled(self):
        q=self.saved();q.update(status='expired',expired_at='earlier');self.save(q)
        self.scan(RPC(500,[transfer()]),lambda *_:[{'peer':'test'}])
        self.assertEqual(self.saved()['status'],'fulfilled')
        self.assertEqual(self.saved()['expired_at'],'earlier')

    def test_no_payment_expires_only_after_complete_scan(self):
        self.scan(RPC(500))
        self.assertEqual(self.saved()['status'],'expired')
        self.assertGreaterEqual(self.saved()['reconciliation']['last_scanned_block'],200)

    def test_log_failure_does_not_expire(self):
        rpc=RPC(500);rpc.fail_logs=True
        result=self.scan(rpc)
        self.assertEqual(result['status'],'degraded')
        self.assertEqual(self.saved()['status'],'awaiting_payment')
        self.assertNotIn('reconciliation',self.saved())

    def test_bounded_scan_never_claims_unchecked_expiry(self):
        q=self.saved();q['expires_after_block']=5000;q.pop('quote_hash');q['quote_hash']=digest(q);self.save(q)
        self.scan(RPC(6000),max_chunks=1)
        self.assertEqual(self.saved()['status'],'awaiting_payment')
        self.assertLess(self.saved()['reconciliation']['last_scanned_block'],5000)

    def test_resume_checkpoint(self):
        rpc=RPC(1400)
        self.scan(rpc,max_chunks=1)
        rpc.calls.clear()
        self.scan(rpc,max_chunks=1)
        low=next(p[0]['fromBlock'] for m,p in rpc.calls if m=='eth_getLogs')
        self.assertEqual(int(low,16),600)

    def test_late_payment_is_review_not_revenue(self):
        out=self.scan(RPC(400,[transfer(block=220)]),lambda *_:[{'peer':'test'}])
        self.assertEqual(self.saved()['status'],'late_payment_review')
        self.assertEqual(out['verified_external_revenue_atomic'],0)
        self.assertEqual(out['fulfilled'],[])

    def test_expired_order_still_detects_later_transfer(self):
        self.scan(RPC(210))
        self.scan(RPC(300,[transfer(block=250)]))
        self.assertEqual(self.saved()['status'],'late_payment_review')

    def test_paid_is_saved_before_failed_delivery(self):
        def fail(*args):
            self.assertEqual(self.saved()['status'],'paid_delivery_pending')
            self.assertIn('settlement',self.saved())
            raise RuntimeError('test')
        self.scan(RPC(300,[transfer()]),fail)
        self.assertEqual(self.saved()['status'],'paid_delivery_pending')

    def test_delivery_retry_never_needs_new_payment(self):
        self.scan(RPC(300,[transfer()]))
        old=self.saved()['settlement']
        self.scan(RPC(1000,[transfer()]),lambda *_:[{'peer':'test'}])
        self.assertEqual(self.saved()['status'],'fulfilled')
        self.assertEqual(self.saved()['settlement'],old)

    def test_reincluded_payment_after_expiry_requires_review(self):
        self.scan(RPC(300,[transfer(block=180)]))
        old=self.saved()['settlement']
        calls=[]
        out=self.scan(RPC(400,[transfer(block=220)]),lambda *_:calls.append(1) or [{'peer':'test'}])
        saved=self.saved()
        self.assertEqual(calls,[])
        self.assertEqual(out['fulfilled'],[])
        self.assertEqual(saved['status'],'late_payment_review')
        self.assertEqual(saved['settlement']['block_number'],220)
        self.assertEqual(saved['prior_settlements'],[old])

    def test_reincluded_on_time_payment_updates_evidence_before_delivery(self):
        self.scan(RPC(300,[transfer(block=180)]))
        def route(*_):
            self.assertEqual(self.saved()['settlement']['block_number'],190)
            return [{'peer':'test'}]
        self.scan(RPC(400,[transfer(block=190)]),route)
        self.assertEqual(self.saved()['status'],'fulfilled')
        self.assertEqual(self.saved()['settlement']['block_number'],190)

    def test_noncanonical_match_does_not_skip_corrected_payment(self):
        rpc=RPC(300,[transfer()])
        rpc.canonical_override={180:bh(999180),295:bh(999295)}
        out=self.scan(rpc)
        self.assertEqual(out['status'],'degraded')
        self.assertNotIn('reconciliation',self.saved())
        corrected=transfer();corrected['blockHash']=bh(999180)
        rpc=RPC(300,[corrected]);rpc.canonical_override={180:bh(999180),295:bh(999295)}
        self.scan(rpc,lambda *_:[{'peer':'test'}])
        self.assertEqual(self.saved()['status'],'fulfilled')

    def test_midscan_reorg_does_not_advance_cursor(self):
        class ChangingRPC(RPC):
            high_reads=0
            def __call__(self,method,params):
                if method=='eth_getBlockByNumber' and params[0]==hex(295):
                    self.high_reads+=1
                    return {'hash':bh(295 if self.high_reads==1 else 999295)}
                return super().__call__(method,params)
        out=self.scan(ChangingRPC(300))
        self.assertEqual(out['status'],'degraded')
        self.assertNotIn('reconciliation',self.saved())

    def test_inconsistent_receipt_does_not_skip_retry(self):
        class WrongTransactionRPC(RPC):
            def __call__(self,method,params):
                value=super().__call__(method,params)
                if method=='eth_getTransactionReceipt':
                    value['transactionHash']='0x'+'99'*32
                return value
        failed=RPC(300,[transfer()]);failed.receipt_status='0x0'
        for stale in (failed,WrongTransactionRPC(300,[transfer()])):
            with self.subTest(type=type(stale).__name__):
                self.save(quote())
                out=self.scan(stale)
                self.assertEqual(out['status'],'degraded')
                self.assertNotIn('reconciliation',self.saved())
                self.scan(RPC(310,[transfer()]),lambda *_:[{'peer':'test'}])
                self.assertEqual(self.saved()['status'],'fulfilled')

    def test_backlog_is_degraded_until_scan_catches_up(self):
        out=self.scan(RPC(1400),max_chunks=1)
        self.assertEqual(out['status'],'degraded')
        self.assertEqual(out['backlog_order_ids'],['o1'])
        out=self.scan(RPC(1400))
        self.assertEqual(out['status'],'ok')
        self.assertEqual(out['backlog_order_ids'],[])

    def test_payment_recheck_blocks_disappearing_transfer(self):
        self.scan(RPC(300,[transfer()]))
        rpc=RPC(400,[transfer()]);rpc.receipt_status='0x0'
        out=self.scan(rpc,lambda *_:[{'peer':'test'}])
        self.assertEqual(out['status'],'degraded')
        self.assertEqual(out['review_order_ids'],['o1'])
        self.assertEqual(self.saved()['status'],'paid_delivery_pending')
        self.assertTrue(any(e['kind']=='payment_recheck_required' for e in self.saved()['recovery_events'].values()))

    def test_receipt_hash_covers_declared_receipt_fields(self):
        self.scan(RPC(300,[transfer()]),lambda *_:[{'peer':'test'}])
        o=self.saved()
        self.assertEqual(o['receipt_hash'],digest({k:o[k] for k in ('order_id','quote_hash','settlement','result','fulfilled_at')}))

    def test_empty_result_does_not_mark_fulfilled(self):
        self.scan(RPC(300,[transfer()]),lambda *_:[])
        self.assertEqual(self.saved()['status'],'paid_delivery_pending')

    def test_replay_does_not_deliver_twice(self):
        calls=[]
        rpc=RPC(300,[transfer()])
        for _ in range(2):self.scan(rpc,lambda *_:calls.append(1) or [{'peer':'test'}])
        self.assertEqual(calls,[1])

    def test_wrong_chain_fails_without_mutation(self):
        rpc=RPC();rpc.chain=1
        with self.assertRaisesRegex(ValueError,'wrong_rpc_chain'):self.scan(rpc)
        self.assertEqual(self.saved()['status'],'awaiting_payment')

    def test_tampered_quote_is_rejected(self):
        q=self.saved();q['amount_atomic']=5;self.save(q)
        out=self.scan(RPC())
        self.assertEqual(out['status'],'degraded')
        self.assertEqual(out['orders_examined'],0)

    def test_amount_only_log_is_not_payment(self):
        log=transfer();del log['topics']
        self.scan(RPC(300,[log]))
        self.assertNotIn('settlement',self.saved())

    def test_wrong_token_payee_topic_removed_and_amount_rejected(self):
        for field,val in [('address','0x'+'ef'*20),('topics',[TOPIC,'0x'+'0'*24+PAYER[2:],'0x'+'0'*64]),('removed',True),('data','0x1')]:
            with self.subTest(field=field):
                log=transfer();log[field]=val
                self.assertIsNone(verified_hit(quote(),log,100,250,RPC(logs=[log])))

    def test_unconfirmed_log_cannot_match(self):
        self.scan(RPC(182,[transfer()]))
        self.assertNotIn('settlement',self.saved())

    def test_failed_transaction_rejected(self):
        rpc=RPC(300,[transfer()]);rpc.receipt_status='0x0'
        self.scan(rpc)
        self.assertNotIn('settlement',self.saved())

    def test_noncanonical_block_rejected(self):
        rpc=RPC(300,[transfer()]);rpc.canonical_override[180]=bh(99)
        self.scan(rpc)
        self.assertNotIn('settlement',self.saved())

    def test_changed_scan_checkpoint_replays_history(self):
        rpc=RPC(300);self.scan(rpc)
        rpc.canonical_override[295]=bh(99);rpc.logs=[transfer()]
        self.scan(rpc,lambda *_:[{'peer':'test'}])
        self.assertEqual(self.saved()['status'],'fulfilled')

    def test_duplicate_amount_orders_need_review(self):
        self.save(quote('o2'))
        self.scan(RPC(300,[transfer()]),lambda *_:[{'peer':'test'}])
        self.assertEqual(self.saved()['status'],'ambiguous_payment_review')
        self.assertEqual(self.saved('o2')['status'],'ambiguous_payment_review')

    def test_warning_is_durable_and_has_stable_id(self):
        first=self.scan(RPC(150))['events']
        second=self.scan(RPC(160))['events']
        self.assertEqual(first[0]['id'],second[0]['id'])
        self.assertEqual(first[0]['kind'],'quote_deadline_near')

    def test_corrupt_file_is_not_silently_empty(self):
        (self.root/'bad.json').write_text('{')
        out=self.scan(RPC())
        self.assertEqual(out['status'],'degraded')
        self.assertEqual(len(out['errors']),1)

    def test_validation_does_not_mutate_quote_deadline(self):
        q=self.saved()
        self.scan(RPC(300,[transfer()]),lambda *_:[{'peer':'test'}])
        self.assertEqual(self.saved()['expires_after_block'],q['expires_after_block'])
        self.assertEqual(self.saved()['quote_hash'],q['quote_hash'])

if __name__=='__main__':unittest.main()
