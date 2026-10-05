#!/usr/bin/env python3
"""Receiving-only quote service. Reconciliation is delegated to payment_recovery."""
from __future__ import annotations
import argparse, hashlib, json, re, time
from pathlib import Path
from urllib import request
from .payment_recovery import atomic_write, address, validate_order

BASE_RPC='https://mainnet.base.org'
USDC='0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913'
TRANSFER_TOPIC='0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'
CHAIN_ID=8453
BASE_PRICE_ATOMIC=10000
SURCHARGE_SLOTS=5000
CONFIRMATIONS=5
EXPIRY_BLOCKS=1800

def now(): return time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
def canonical(v): return json.dumps(v,sort_keys=True,separators=(',',':'))
def sha(v): return hashlib.sha256(canonical(v).encode()).hexdigest()
def rpc(method,params,rpc_url=BASE_RPC):
    body=json.dumps({'jsonrpc':'2.0','id':1,'method':method,'params':params}).encode()
    req=request.Request(rpc_url,data=body,headers={'content-type':'application/json','user-agent':'A0-direct-usdc/2'})
    with request.urlopen(req,timeout=20) as response:
        raw=response.read(2_000_001)
    if len(raw)>2_000_000: raise RuntimeError('RPC response too large')
    value=json.loads(raw)
    if value.get('error'):raise RuntimeError('Base RPC error')
    return value['result']
def block_number(rpc_fn=rpc): return int(rpc_fn('eth_blockNumber',[]),16)
def topic_address(addr): return '0x'+'0'*24+address(addr)[2:]
def format_usdc(amount):
    amount=int(amount)
    return str(amount//1_000_000)+'.'+str(amount%1_000_000).zfill(6)
def load_orders(root):
    root=Path(root)
    return [(p,json.loads(p.read_text(encoding='utf-8'))) for p in sorted(root.glob('*.json'))] if root.exists() else []
def allocate_amount(order_id,orders):
    # Legacy amount-only invoices cannot safely reuse expired amount slots.
    used={int(v['amount_atomic']) for _,v in orders}
    start=int(hashlib.sha256(order_id.encode()).hexdigest()[:12],16)%SURCHARGE_SLOTS
    for i in range(SURCHARGE_SLOTS):
        amount=BASE_PRICE_ATOMIC+(start+i)%SURCHARGE_SLOTS
        if amount not in used:return amount
    raise RuntimeError('invoice amount capacity reached; migrate invoice binding before accepting more')
def create_quote(*,orders_dir,order_id,query,requester,comment_id,issue_number,pay_to,rpc_fn=rpc):
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,119}',str(order_id)):
        raise ValueError('invalid order_id')
    address(pay_to)
    orders=load_orders(orders_dir)
    path=Path(orders_dir)/(order_id+'.json')
    if path.exists():
        prior=json.loads(path.read_text(encoding='utf-8'))
        validate_order(prior,pay_to)
        if prior['query']!=str(query)[:1000] or prior['requester']!=str(requester) or prior['comment_id']!=int(comment_id) or prior['issue_number']!=int(issue_number):
            raise ValueError('order_id conflict')
        return prior
    latest=int(rpc_fn('eth_blockNumber',[]),16)
    amount=allocate_amount(order_id,orders)
    order={'schema_version':1,'order_id':order_id,'issue_number':int(issue_number),'comment_id':int(comment_id),
        'requester':str(requester),'service':'read_only_route_selection','query':str(query)[:1000],'limit':3,
        'network':'eip155:8453','chain_id':CHAIN_ID,'asset':'USDC','token_contract':USDC,'pay_to':pay_to,
        'amount_atomic':amount,'amount_usdc':format_usdc(amount),'from_block':latest,
        'expires_after_block':latest+EXPIRY_BLOCKS,'confirmations':CONFIRMATIONS,'status':'awaiting_payment','created_at':now()}
    order['quote_hash']=sha(order)
    atomic_write(path,order)
    return order

def transfer_logs(order,latest,rpc_fn=rpc):
    """Compatibility discovery helper; returned logs are not verified payments."""
    end=min(latest-int(order.get('confirmations',CONFIRMATIONS)),order['expires_after_block'])
    if end<order['from_block']:return []
    return rpc_fn('eth_getLogs',[{'address':order['token_contract'],'fromBlock':hex(order['from_block']),
        'toBlock':hex(end),'topics':[TRANSFER_TOPIC,None,topic_address(order['pay_to'])]}]) or []

def scan_orders(orders_dir,pay_to,rpc_fn=rpc,route_fn=None):
    from .payment_recovery import scan_orders as recover
    return recover(orders_dir,pay_to,rpc_fn,route_fn)

def cli():
    parser=argparse.ArgumentParser();subs=parser.add_subparsers(dest='cmd',required=True)
    quote=subs.add_parser('quote');quote.add_argument('--orders-dir',required=True);quote.add_argument('--order-id',required=True)
    quote.add_argument('--query',required=True);quote.add_argument('--requester',required=True);quote.add_argument('--comment-id',required=True,type=int)
    quote.add_argument('--issue-number',required=True,type=int);quote.add_argument('--pay-to',required=True)
    scan=subs.add_parser('scan');scan.add_argument('--orders-dir',required=True);scan.add_argument('--pay-to',required=True)
    args=parser.parse_args()
    try:
        if args.cmd=='quote':out=create_quote(orders_dir=args.orders_dir,order_id=args.order_id,query=args.query,requester=args.requester,comment_id=args.comment_id,issue_number=args.issue_number,pay_to=args.pay_to)
        else:
            from .mesh import Mesh
            mesh=Mesh()
            out=scan_orders(args.orders_dir,args.pay_to,route_fn=lambda query,limit:mesh.route(query,limit=limit))
    except Exception as error:
        out={'status':'unavailable','errors':[{'error':type(error).__name__}],'events':[],'fulfilled':[]}
    print(json.dumps(out,indent=2))
    if out.get('status') in ('degraded','unavailable'):raise SystemExit(1)
if __name__=='__main__':cli()
