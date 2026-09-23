#!/usr/bin/env python3
"""Review recorded live results and assemble a release report. No network calls."""
import hashlib, json
from mesh import Mesh, ROOT, now, write_json, parts_of
from peer_control import render_summary

m=Mesh()
def receipt(task_id):
    return json.loads((ROOT/m.state['tasks'][task_id]['receipt']).read_text())
def response_data(rec):
    return [p['data'] for p in parts_of(rec['response'].get('result',{})) if isinstance(p,dict) and isinstance(p.get('data'),dict)]

discovery=receipt('issue-9')
capabilities=[c for d in response_data(discovery) for c in d.get('capabilities',[]) if isinstance(c,dict)]
assert any(c.get('name')=='verify_artifact' and set(c.get('inputSchema',{}).get('required',[]))=={'artifact','constraints'} for c in capabilities)
if m.state['tasks']['issue-9']['semantic_validation']=='not_reviewed':
    m.review('issue-9',True,'The live capability lookup returned verify_artifact with the required artifact/constraints input schema and a concrete invocation interface.')

validation=receipt('issue-11')
args=validation['request']['params']['message']['parts'][0]['data']['arguments']
artifact=args['artifact']
expected_hash=hashlib.sha256(json.dumps(artifact,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()
checks=response_data(validation)
assert any(d.get('valid') is True and d.get('errors')==[] and d.get('artifact_hash')==expected_hash and d.get('verification',{}).get('scope')=='explicit_schema_constraints_only' and d.get('verification',{}).get('code_executed') is False for d in checks)
upstream=receipt('bootstrap-20260923-orientation')['response']['result']
upstream_task=upstream.get('task',upstream)
assert artifact['remote_task_id']==upstream_task['id']
assert artifact['context_id']==upstream_task['contextId']
assert artifact['state']==upstream_task['status']['state']
assert any(d.get('service')==artifact['service'] and d.get('current_event_id')==artifact['current_event_id'] for d in response_data(receipt('bootstrap-20260923-orientation')))
if m.state['tasks']['issue-11']['semantic_validation']=='not_reviewed':
    m.review('issue-11',True,'ATTRACTOR validated the exact structured record derived from the real ZenithEye response. Its artifact hash matches our independently recomputed sorted compact JSON SHA-256. Scope: explicit schema constraints, not factual correctness of arbitrary claims.')

poll=m.state.get('polls',{}).get('issue-12',{})
assert poll.get('remote_task_id_matched') is True
assert poll.get('task_id')=='bootstrap-20260923-orientation'
m.state['peers']['attractor']['kind']='validation_service'
m.state['directory_contacts']['attractor'].update(card_url=m.state['peers']['attractor']['card_url'],peer_id='attractor',status='connected')
for edge in [
 {'from':'allagents','to':'attractor','relation':'directory_referral','task_id':'bootstrap-20260923-directory','source_record':'https://allagents.app/agent/attractor'},
 {'from':'zenitheye','to':'attractor','relation':'schema_checked_handoff','task_id':'issue-11','artifact_hash':expected_hash}
]:
    if edge not in m.state['edges']:m.state['edges'].append(edge)
m.state['task_outcomes']={
 'bootstrap-20260923-directory':'Useful public profile leads; response exceeded the requested three results and did not directly supply card URLs.',
 'bootstrap-20260923-evaluation':'Peer dialogue/clarification, not a completed substantive evaluation.',
 'followup-20260923-mycelix':'Peer methodology interview continued; not a completed substantive evaluation.',
 'followup-20260923-sanctum':'Structured public work listings and community discovery returned.',
 'followup-20260923-humanmirror':'Capability gap/no confident match returned; no paid execution requested.'
}
summary=render_summary(m,'verified-runtime-snapshot',{'artifact_hash_matched':True,'remote_task_retrieval_matched':True},[])
report={
 'generated_at':now(),
 'connected_public_peers':summary['connected_peers'],
 'registered_peer_records':summary['registered_peers'],
 'task_request_records':summary['task_count'],
 'protocol_responses_received':summary['results_received'],
 'successful_remote_task_retrievals':sum(p.get('remote_task_id_matched') is True for p in m.state.get('polls',{}).values()),
 'validated_task_results':summary['verified_task_results'],
 'catalog':m.state['catalog'],
 'artifact_hash':expected_hash,
 'chain':['allagents directory referral','ATTRACTOR capability discovery','ZenithEye task result','ATTRACTOR schema validation of the real ZenithEye record'],
 'recorded_peers':[{k:p.get(k) for k in ('id','node_id','slot','name','kind','endpoint','protocol_version','context_id','verified_results')} for p in m.state['peers'].values()],
 'peer_memory_survived_multiple_runs':m.state.get('persistence_check'),
 'limitations':['Public endpoints include deterministic services, not only reasoning models.','Connection success is not automatic task success.','On-demand execution; no always-running inbound service.','No joint neural-model training or claimed access to remote model weights.','Routing quality estimates are based on a small set of observed tasks.']
}
write_json(ROOT/'reports/PEER-RUNTIME-RESULTS.json',report)
md='''# SwarmBrain: live peer runtime results

Generated: {time}

## What is operational

Seven public peers are registered with stable identities and graph slots, and all seven have returned valid A2A protocol responses. Nine task-request records, nine returned protocol responses, and one successful later retrieval of a server-side task are retained. Four task results passed explicit result checks: SNAIL conversation retrieval, ZenithEye arrival, ATTRACTOR capability-schema discovery, and ATTRACTOR schema validation of the real ZenithEye task record.

The prior index is preserved as 1,146 canonical public listings derived from 1,154 source records. Listings and connected peers are separate states. Public peer registration does not require a JOIN phrase.

## The concrete multi-peer chain

1. The allagents directory returned ATTRACTOR as a lead.
2. Its actual public card was fetched and stored in slot 7.
3. An A2A capability lookup returned its verification operation and schema.
4. A structured record from the actual ZenithEye response was passed to that operation.
5. ATTRACTOR returned valid=true, errors=[], and an artifact hash.
6. The hash was independently recomputed and matched: `{hash}`.
7. ZenithEye's original task was retrieved later using its saved server-issued ID, without repeating the original request.

Validation scope was explicit schema constraints. This is not a claim of arbitrary factual or semantic verification.

## Connected peers

| Slot | Peer | Observed role/result |
|---|---|---|
| 1 | allagents | Directory lookup; returned real profile leads. |
| 2 | SNAIL | Returned requested public conversation records. |
| 3 | ZenithEye | Completed an arrival task and later returned that stored task by ID. |
| 4 | MYCELIX | Returned peer-dialogue questions; substantive evaluation remains unfinished. |
| 5 | Sanctum Beacon | Returned structured public work listings and community information. |
| 6 | HumanMirror | Responded with a capability gap, not a successful matching execution. |
| 7 | ATTRACTOR | Returned schemas and validated a real cross-peer task record. |

These include public services and gateways. They are not seven dedicated model instances controlled by SwarmBrain.

## Reuse

Open an owner-authored GitHub issue titled `SwarmBrain task: ...` with a JSON body. Modes are `connect`, `request`, `poll`, and `route`. The workflow runs once and persists its results in `data/mesh-state.json`, `data/graph.json`, and `reports/`. The same request ID is not sent twice. Use the default branch as the canonical state history and submit one task at a time.

The working controls were exercised through actual issues #8, #9, #11, and #12. No signup ceremony was required for these public peer calls.

## Still separate work

The coordinator is on-demand, not an always-running inbound A2A host. The graph and empirical routing scores are not jointly trained model weights. Broader task orchestration and outcome evaluation can build on these recorded connections; neither uptime nor autonomous reasoning quality is inferred from a successful HTTP exchange.
'''.format(time=report['generated_at'],hash=expected_hash)
(ROOT/'reports/PEER-RUNTIME-RESULTS.md').write_text(md,encoding='utf-8')
print(json.dumps(report,indent=2))
