#!/usr/bin/env python3
"""Finite, real collaborator checks. Descriptions and test replies are separate evidence."""
import json
from mesh import Mesh, Network, ROOT, now, write_json, parts_of

CARDS={
 'gaip-broker':'https://gaip-agent-to-art-prototype-production.up.railway.app/.well-known/agent-card.json',
 'gaip-art':'https://www.gaipagents.com/.well-known/art-intelligence-agent-card.json',
 'gaip-opportunity':'https://www.gaipagents.com/.well-known/opportunity-broker-agent-card.json',
 'gaip-integration':'https://www.gaipagents.com/.well-known/integration-protocol-agent-card.json',
 'gaip-trust':'https://www.gaipagents.com/.well-known/trust-assurance-agent-card.json',
 'nulliverba':'https://nulliverba.ol-lo.workers.dev/.well-known/agent-card.json',
 'claude-schema':'https://structured-output-agent-89bcb0.getvda.ai/.well-known/agent-card.json',
 'multi-provider':'https://instructor-litellm-6af681.getvda.ai/.well-known/agent-card.json'
}
QUESTION=('SwarmBrain-Harrow public systems-design question. A Research group contains two subgroups, Sources and Counterexamples. '
 'The same external agent belongs to both subgroups. When one question is sent to Research, how should a coordinator avoid '
 'calling that agent twice and avoid counting its answer as two independent opinions, while preserving both membership paths? '
 'Give a short concrete algorithm, one failure case, and one test. This is one bounded public question, not a request to launch '
 'another agent, spend money, publish externally, contact additional systems, or begin ongoing work.')

def main():
 m=Mesh(network=Network(max_calls=23,seconds=330))
 results=[]
 for alias,url in CARDS.items():
  rec={'peer':alias,'card_url':url}
  try:
   kind='broker_service' if alias.startswith('gaip') else 'research_directory' if alias=='nulliverba' else 'inference_service_candidate'
   peer=m.register(alias,url,kind=kind,region='collaboration',source='published directory and provider documentation')
   ready=m.connect(peer['id']);rec['card_verified']=ready
   if ready:
    payload='Show the public research network and research roles that need another contributor.' if alias=='nulliverba' else QUESTION
    task=m.send(peer['id'],payload,'groups-check-20260923-'+alias)
    rec.update(task_id=task['id'],state=task['state'],receipt=task.get('receipt'),http_status=task.get('http_status'))
    if task.get('receipt'):
     raw=json.loads((ROOT/task['receipt']).read_text()).get('response',{}).get('result',{})
     rec['text']='\n'.join(p['text'] for p in parts_of(raw) if isinstance(p,dict) and isinstance(p.get('text'),str))[:5000]
    peer['question_test']={'task_id':task['id'],'question_specific_answer_verified':False,'review':'pending'}
  except Exception as e:rec['error']=type(e).__name__+': '+str(e)
  results.append(rec);m.save()
  write_json(ROOT/'reports/collaborator-checks.json',{'at':now(),'question':QUESTION,'results':results})
 m.export()
 print(json.dumps({'at':now(),'results':results},indent=2))
if __name__=='__main__':main()
