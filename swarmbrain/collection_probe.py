"""Read-only buyer work probe using documented BasedAgents money units.
No identity creation, claim, message, wallet signature or transaction is made.
"""
import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from urllib import request

SOURCE='https://api.basedagents.ai/v1/tasks?status=open'
CONTRACT='https://basedagents.ai/.well-known/agent.json'

def summarize(data):
    rows=data if isinstance(data,list) else data.get('tasks') if isinstance(data,dict) else None
    if not isinstance(rows,list):raise ValueError('unsupported_task_schema')
    out=[]
    for row in rows[:50]:
        if not isinstance(row,dict):continue
        bounty=row.get('bounty') or {}
        amount=None
        if isinstance(bounty,dict) and bounty.get('token',bounty.get('currency',bounty.get('asset')))=='USDC' and bounty.get('network')=='eip155:8453':
            raw=bounty.get('amount_atomic',bounty.get('amount'))
            if isinstance(raw,str) and raw.isdigit():amount=str(Decimal(raw)/1_000_000)
            elif raw is None and bounty.get('amount_display') is not None:
                try:
                    num=Decimal(str(bounty['amount_display']))
                    if num.is_finite() and num>=0:amount=str(num)
                except InvalidOperation:pass
        escrow=row.get('escrow') if isinstance(row.get('escrow'),dict) else {}
        out.append({'task_id':row.get('task_id',row.get('id')),'title':row.get('title'),
            'requirements_excerpt':str(row.get('description',''))[:1200],
            'acceptance_criteria':row.get('acceptance_criteria'),
            'budget_usdc':amount,'raw_budget_public':bounty,'status':row.get('status'),
            'deadline':row.get('deadline',row.get('expires_at')),'claimable':row.get('claimable'),
            'escrow_report':escrow.get('status'),'funding_verified':False,
            'source':SOURCE,'next_action':'qualify_identity_delivery_terms_before_claim'})
    return {'source':SOURCE,'money_schema_source':CONTRACT,'status':'ok',
        'observed_at':datetime.now(timezone.utc).isoformat(),'rows_examined':len(out),
        'paid_budget_count':sum(Decimal(x['budget_usdc'] or '0')>0 for x in out),
        'tasks':out,'claims_made':0,'payments_collected':0,'coverage':'bounded_first_response'}

def main():
    try:
        req=request.Request(SOURCE,headers={'accept':'application/json','user-agent':'A0-collection-probe/1'})
        with request.urlopen(req,timeout=20) as response:raw=response.read(1_000_001)
        if len(raw)>1_000_000:raise ValueError('response_too_large')
        out=summarize(json.loads(raw))
    except Exception as error:
        out={'source':SOURCE,'status':'unavailable','error':type(error).__name__,'claims_made':0,'payments_collected':0}
    print(json.dumps(out,indent=2))
if __name__=='__main__':main()
