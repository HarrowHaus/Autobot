#!/usr/bin/env python3
import argparse,json,os
from verifier import HTTP,Verifier,parse_claim_text

def main():
    p=argparse.ArgumentParser(description="Read-only RustChain bounty claim verifier")
    p.add_argument("--claim-json")
    p.add_argument("--claim-text")
    p.add_argument("--owner",default="Scottcjn")
    p.add_argument("--node",default=os.environ.get("RUSTCHAIN_NODE_URL","https://50.28.86.131"))
    args=p.parse_args()
    if bool(args.claim_json)==bool(args.claim_text):
        p.error("provide exactly one of --claim-json or --claim-text")
    if args.claim_json:
        with open(args.claim_json,encoding="utf-8") as f:
            claim=json.load(f)
    else:
        with open(args.claim_text,encoding="utf-8") as f:
            claim=parse_claim_text(f.read())
    v=Verifier(HTTP(github_token=os.environ.get("GITHUB_TOKEN")),owner=args.owner,node=args.node)
    print(json.dumps(v.verify(claim),indent=2,sort_keys=True))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
