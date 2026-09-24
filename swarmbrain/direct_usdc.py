#!/usr/bin/env python3
"""Direct Base USDC payment collector for bounded SwarmBrain services."""
from __future__ import annotations
import argparse, hashlib, json, os, time
from pathlib import Path
from urllib import request

BASE_RPC="https://mainnet.base.org"
USDC="0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
TRANSFER_TOPIC="0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
CHAIN_ID=8453
BASE_PRICE_ATOMIC=10_000
SURCHARGE_SLOTS=5_000
CONFIRMATIONS=5
EXPIRY_BLOCKS=1800

def now(): return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
def canonical(v): return json.dumps(v,sort_keys=True,separators=(",",":"))
def sha(v): return hashlib.sha256(canonical(v).encode()).hexdigest()
def rpc(method,params,rpc_url=BASE_RPC):
    body=json.dumps({"jsonrpc":"2.0","id":1,"method":method,"params":params}).encode()
    req=request.Request(rpc_url,data=body,headers={"content-type":"application/json","user-agent":"A0-direct-usdc/1"})
    with request.urlopen(req,timeout=20) as r:
        value=json.loads(r.read().decode())
    if value.get("error"): raise RuntimeError("Base RPC error: "+str(value["error"]))
    return value["result"]
def block_number(rpc_fn=rpc): return int(rpc_fn("eth_blockNumber",[]),16)
def topic_address(addr):
    raw=str(addr).lower()
    if not raw.startswith("0x") or len(raw)!=42: raise ValueError("invalid EVM address")
    int(raw[2:],16)
    return "0x"+"0"*24+raw[2:]
def format_usdc(amount): return f"{int(amount)/1_000_000:.6f}"
def load_orders(root):
    root=Path(root); out=[]
    if not root.exists(): return out
    for p in sorted(root.glob("*.json")):
        try: out.append((p,json.loads(p.read_text(encoding="utf-8"))))
        except Exception: continue
    return out
def allocate_amount(order_id,orders):
    used={int(v.get("amount_atomic",0)) for _,v in orders if v.get("status") in ("awaiting_payment","paid")}
    start=BASE_PRICE_ATOMIC+(int(hashlib.sha256(order_id.encode()).hexdigest()[:12],16)%SURCHARGE_SLOTS)
    for i in range(SURCHARGE_SLOTS):
        amount=BASE_PRICE_ATOMIC+((start-BASE_PRICE_ATOMIC+i)%SURCHARGE_SLOTS)
        if amount not in used:return amount
    raise RuntimeError("no quote slots available")
def create_quote(*,orders_dir,order_id,query,requester,comment_id,issue_number,pay_to,rpc_fn=rpc):
    orders=load_orders(orders_dir)
    path=Path(orders_dir)/(order_id+".json")
    if path.exists(): return json.loads(path.read_text())
    latest=int(rpc_fn("eth_blockNumber",[]),16)
    amount=allocate_amount(order_id,orders)
    order={"schema_version":1,"order_id":order_id,"issue_number":int(issue_number),"comment_id":int(comment_id),
      "requester":str(requester),"service":"read_only_route_selection","query":str(query)[:1000],
      "limit":3,"network":"eip155:8453","chain_id":CHAIN_ID,"asset":"USDC","token_contract":USDC,
      "pay_to":pay_to,"amount_atomic":amount,"amount_usdc":format_usdc(amount),
      "from_block":latest,"expires_after_block":latest+EXPIRY_BLOCKS,"confirmations":CONFIRMATIONS,
      "status":"awaiting_payment","created_at":now()}
    order["quote_hash"]=sha(order)
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(order,indent=2)+"\n",encoding="utf-8")
    return order
def transfer_logs(order,latest,rpc_fn=rpc):
    safe=max(0,latest-int(order.get("confirmations",CONFIRMATIONS)))
    end=min(safe,int(order["expires_after_block"]))
    if end<int(order["from_block"]):return []
    filt={"address":order["token_contract"],"fromBlock":hex(int(order["from_block"])),
      "toBlock":hex(end),"topics":[TRANSFER_TOPIC,None,topic_address(order["pay_to"])]}
    return rpc_fn("eth_getLogs",[filt]) or []
def match_payment(order,logs,used_txs):
    amount=int(order["amount_atomic"])
    for log in logs:
        tx=str(log.get("transactionHash") or "").lower()
        if not tx or tx in used_txs: continue
        try: observed=int(log.get("data","0x0"),16)
        except ValueError: continue
        if observed!=amount: continue
        return {"transaction":tx,"block_number":int(log["blockNumber"],16),
          "log_index":int(log["logIndex"],16),"amount_atomic":observed}
    return None
def scan_orders(orders_dir,pay_to,rpc_fn=rpc,route_fn=None):
    rows=load_orders(orders_dir); latest=int(rpc_fn("eth_blockNumber",[]),16)
    used={str(v.get("settlement",{}).get("transaction","")).lower() for _,v in rows if v.get("settlement")}
    used.discard("")
    fulfilled=[]; expired=[]
    for path,order in rows:
        if order.get("status")!="awaiting_payment":continue
        if str(order.get("pay_to","")).lower()!=str(pay_to).lower():continue
        if latest>int(order["expires_after_block"])+int(order.get("confirmations",CONFIRMATIONS)):
            order["status"]="expired";order["expired_at"]=now();expired.append(order["order_id"])
            path.write_text(json.dumps(order,indent=2)+"\n");continue
        hit=match_payment(order,transfer_logs(order,latest,rpc_fn),used)
        if not hit:continue
        used.add(hit["transaction"]);order["settlement"]={**hit,"confirmed_at":now(),"confirmed_latest_block":latest}
        order["status"]="paid"
        result=route_fn(order["query"],int(order.get("limit",3))) if route_fn else None
        order["result"]=result;order["fulfilled_at"]=now();order["status"]="fulfilled"
        order["receipt_hash"]=sha({k:v for k,v in order.items() if k!="receipt_hash"})
        path.write_text(json.dumps(order,indent=2)+"\n");fulfilled.append(order)
    return {"latest_block":latest,"fulfilled":fulfilled,"expired":expired}
def cli():
    p=argparse.ArgumentParser();s=p.add_subparsers(dest="cmd",required=True)
    q=s.add_parser("quote");q.add_argument("--orders-dir",required=True);q.add_argument("--order-id",required=True)
    q.add_argument("--query",required=True);q.add_argument("--requester",required=True);q.add_argument("--comment-id",required=True,type=int)
    q.add_argument("--issue-number",required=True,type=int);q.add_argument("--pay-to",required=True)
    sc=s.add_parser("scan");sc.add_argument("--orders-dir",required=True);sc.add_argument("--pay-to",required=True)
    a=p.parse_args()
    if a.cmd=="quote":out=create_quote(orders_dir=a.orders_dir,order_id=a.order_id,query=a.query,requester=a.requester,comment_id=a.comment_id,issue_number=a.issue_number,pay_to=a.pay_to)
    else:
        from .mesh import Mesh
        mesh=Mesh()
        out=scan_orders(a.orders_dir,a.pay_to,route_fn=lambda query,limit:mesh.route(query,limit=limit))
    print(json.dumps(out,indent=2))
if __name__=="__main__":cli()
