#!/usr/bin/env python3
"""External product-factory adapter. Runs a configured OSS factory without vendoring it."""
from __future__ import annotations
import argparse,json,os,subprocess
from pathlib import Path

def run(contract_path:str,out_path:str):
    contract=json.loads(Path(contract_path).read_text(encoding="utf-8"))
    cmd=os.environ.get("A0_PRODUCT_FACTORY_CMD","").strip()
    if not cmd:
        result={"status":"rejected","reason":"A0_PRODUCT_FACTORY_CMD_not_configured","contract":contract}
    else:
        env=dict(os.environ); env["A0_OPPORTUNITY_CONTRACT"]=json.dumps(contract)
        p=subprocess.run(cmd,shell=True,text=True,capture_output=True,timeout=3600,env=env)
        result={"status":"built" if p.returncode==0 else "failed","exit_code":p.returncode,
                "stdout":p.stdout[-12000:],"stderr":p.stderr[-6000:],"factory_cmd":cmd.split()[0]}
    Path(out_path).parent.mkdir(parents=True,exist_ok=True)
    Path(out_path).write_text(json.dumps(result,indent=2)+"\n",encoding="utf-8")
    return result
if __name__=="__main__":
    a=argparse.ArgumentParser(); a.add_argument("contract"); a.add_argument("--out",default="reports/merchantbrain/build-receipt.json"); x=a.parse_args()
    print(json.dumps(run(x.contract,x.out),indent=2))
