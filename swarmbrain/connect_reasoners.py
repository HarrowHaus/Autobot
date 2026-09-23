#!/usr/bin/env python3
"""Connect hosted question-answering peers; backend identity remains provider-reported."""
import json
from mesh import Mesh, Network, ROOT, now, write_json, parts_of

CARDS={
 'llm-orchestrator':'https://llm-orchestration-agent-d0a1a1.getvda.ai/.well-known/agent-card.json',
 'traced-claude':'https://traced-llm-proxy-anthropic.getvda.ai/.well-known/agent-card.json',
 'structured-mcp':'https://structured-output-mcp-agent-instructor.getvda.ai/.well-known/agent-card.json',
 'llm-orchestrator-2':'https://llm-orchestration-agent-2-df5979.getvda.ai/.well-known/agent-card.json'
}
QUESTION=('We are building nested groups of independently hosted agents. For a single question, group A contains peers X and Y; '
 'group B contains peers Y and Z. Y answers once, Z times out, and X disagrees with Y. '
 'Give a concrete procedure that preserves both group paths to Y, returns a useful partial answer, and preserves the disagreement '
 'instead of inventing consensus. Give one invariant and one minimal acceptance test. Answer this public design question only; '
 'do not contact other systems, start background work, or spend money. Caller: SwarmBrain-Harrow.')

def main():
 m=Mesh(network=Network(max_calls=12,seconds=280));results=[]
 for alias,url in CARDS.items():
  record={'peer':alias,'card_url':url}
  try:
   p=m.register(alias,url,kind='hosted_question_agent',region='reasoning',source='VDA published agent catalog')
   if m.connect(alias):
    p['group_adapter']='public_text_question'
    t=m.send(alias,QUESTION,'reasoner-check-20260923-'+alias)
    record.update(task_id=t['id'],state=t['state'],receipt=t.get('receipt'),http_status=t.get('http_status'))
    if t.get('receipt'):
     raw=json.loads((ROOT/t['receipt']).read_text()).get('response',{}).get('result',{})
     record['text']='\n'.join(v['text'] for v in parts_of(raw) if isinstance(v,dict) and isinstance(v.get('text'),str))[:10000]
   else:record['state']=p['status']
  except Exception as exc:record['error']=str(exc)
  results.append(record);m.save()
  write_json(ROOT/'reports/reasoner-checks.json',{'at':now(),'question':QUESTION,'results':results})
 # Enable question dispatch for the peer that returned the earlier task-specific answer.
 p=m.state['peers'].get('multi-provider')
 if p:
  p.update(group_adapter='public_text_question',kind='hosted_question_agent')
 m.save();m.export()
 print(json.dumps({'at':now(),'results':results},indent=2))
if __name__=='__main__':main()
