#!/usr/bin/env python3
"""Create real group records from observed peers, then execute one public readiness question."""
import hashlib
import json
from mesh import Mesh, Network, ROOT, now, write_json, parts_of
from groups import GroupNetwork, decoded_answer

QUESTION = ('Answer in at most 160 words. A parent Research node contains Sources={A, Shared} and '
 'Counterexamples={B, Shared}. Shared answers once, B times out, and A disagrees with Shared. '
 'Design the coordinator result contract: give one dispatch rule, a compact data representation, '
 'one invariant, and one acceptance test. Preserve both paths to Shared and do not manufacture '
 'consensus. Answer the question only; no external actions or ongoing work.')

QUESTION_PEERS = ['multi-provider', 'llm-orchestrator', 'traced-claude', 'llm-orchestrator-2']


def answer_from_task(mesh, task_id):
    task = mesh.state['tasks'][task_id]
    record = json.loads((ROOT / task['receipt']).read_text())
    text = '\n'.join(p['text'] for p in parts_of(record['response'].get('result', {}))
                     if isinstance(p, dict) and isinstance(p.get('text'), str))
    return decoded_answer(text)


def main():
    mesh = Mesh(network=Network(max_calls=8, seconds=240))
    ids_before = {p: x['node_id'] for p, x in mesh.state['peers'].items()}
    old_tasks = set(mesh.state['tasks'])
    checked = []
    for peer in QUESTION_PEERS:
        task_id = ('groups-check-20260923-' if peer == 'multi-provider' else 'reasoner-check-20260923-') + peer
        answer = answer_from_task(mesh, task_id)
        if answer.get('application_error') or len(answer['answer_text']) < 100:
            raise ValueError('A required question peer has no observed task-specific reply: ' + peer)
        node = mesh.state['peers'][peer]
        node.update(kind='hosted_question_agent', group_adapter='public_text_question',
                    provider_report=answer['provider_report'], provider_independence_verified=False)
        node['question_test'] = {'task_id': task_id, 'generated_task_specific_text': True,
            'correctness_verified': False, 'note': 'Answer relevance was observed; several initial answers were truncated or imperfect.'}
        checked.append({'peer': peer, 'task_id': task_id, 'provider_report': answer['provider_report']})
    quota_peer = mesh.state['peers'].get('structured-mcp')
    if quota_peer:
        quota_peer.update(status='paused', pause_reason='Provider returned 429 RESOURCE_EXHAUSTED inside a text result; not an answer')
        quota_peer.pop('group_adapter', None)
    mesh.save()
    groups = GroupNetwork(ROOT, mesh)
    definitions = [
        ('design', 'Design contributors', ['multi-provider', 'llm-orchestrator']),
        ('critique', 'Alternative and critical contributors', ['traced-claude', 'llm-orchestrator-2']),
        ('synthesis', 'Synthesis-capable contributor', ['multi-provider']),
        ('reasoning', 'Question-answering group', ['design', 'critique', 'synthesis']),
        ('discovery', 'Public agent and research discovery', ['allagents', 'humanmirror', 'nulliverba']),
        ('commons', 'Public conversations and work context', ['snail', 'zenitheye', 'sanctum']),
        ('research', 'Research and discovery services', ['discovery', 'commons']),
        ('validation', 'Structure and workflow evidence services', ['attractor', 'gaip-broker']),
        ('assurance', 'Validation support', ['validation']),
        ('swarm', 'SwarmBrain', ['reasoning', 'research', 'assurance'])
    ]
    for group_id, label, children in definitions:
        groups.define(group_id, label, children)
    groups.export()
    run = groups.ask('reasoning', QUESTION, 'nested-readiness-20260923', max_peers=4, synthesize=True)
    assert set(run['contributions']) == set(QUESTION_PEERS)
    assert len({c['task_id'] for c in run['contributions'].values()}) == 4
    assert len(run['contributions']['multi-provider']['paths']) == 2
    assert 'multi-provider' in run['children']['design']['contributor_refs']
    assert 'multi-provider' in run['children']['synthesis']['contributor_refs']
    assert all(mesh.state['peers'][p]['node_id'] == ident for p, ident in ids_before.items())
    assert old_tasks.issubset(mesh.state['tasks'])
    snapshot = GroupNetwork(ROOT)
    assert snapshot.plan('reasoning')['paths'] == groups.plan('reasoning')['paths']
    write_json(ROOT / 'reports/group-latest.json', run)
    root_plan = groups.plan('swarm')
    outcome = {
        'generated_at': now(), 'group_count': len(groups.state['groups']),
        'grouped_unique_peer_count': root_plan['unique_peers'],
        'registered_peer_count': len(mesh.state['peers']),
        'reasoning_unique_peers': groups.plan('reasoning')['unique_peers'],
        'reasoning_membership_paths': groups.plan('reasoning')['membership_paths'],
        'question_endpoints': checked, 'readiness_question': QUESTION,
        'readiness_run': 'reports/group-runs/nested-readiness-20260923.json',
        'contributor_requests': len(run['contributions']), 'returned_contributors': run['returned_peers'],
        'synthesis_state': run.get('synthesis', {}).get('state'),
        'synthesis_receipt': run.get('synthesis', {}).get('receipt'),
        'live_deduplication_verified': True, 'prior_peer_ids_preserved': len(ids_before),
        'prior_task_ids_preserved': len(old_tasks), 'group_reload_verified': True,
        'provider_independence_verified': False,
        'provider_note': 'The four question endpoints reported gemini-2.5-flash / vertex-ai. Distinct hosted interfaces do not establish distinct model families or independent operators.',
        'paused_peer': 'structured-mcp', 'background_execution': False,
        'hierarchy': [{'id': g, 'children': c} for g, _, c in definitions],
        'contributions': {p: {'state': c['state'], 'paths': c['paths'], 'receipt': c.get('task_receipt'),
                              'answer_text': c.get('answer_text'), 'provider_report': c.get('provider_report')}
                          for p, c in run['contributions'].items()},
        'synthesized_answer': run.get('synthesis', {}).get('answer_text', ''),
        'test_scope': 'Real outbound calls plus exact request-ID, membership-path, and persistent-state checks. Answer truth/correctness is not automatically certified.'
    }
    write_json(ROOT / 'reports/NESTED-GROUP-RESULTS.json', outcome)
    lines = ['# SwarmBrain nested groups — live results', '', 'Generated: ' + outcome['generated_at'], '',
        f"{outcome['group_count']} coordinator groups; {outcome['grouped_unique_peer_count']} distinct peer leaves in the hierarchy; four hosted question-answering interfaces.", '',
        f"Readiness: {outcome['returned_contributors']} of four contributors returned, with synthesis state `{outcome['synthesis_state']}`.", '',
        '## Group structure', '', '```text',
        'swarm', '  reasoning', '    design: multi-provider, llm-orchestrator',
        '    critique: traced-claude, llm-orchestrator-2', '    synthesis: multi-provider (same peer, reused path)',
        '  research', '    discovery: allagents, humanmirror, nulliverba', '    commons: snail, zenitheye, sanctum',
        '  assurance', '    validation: attractor, gaip-broker', '```', '',
        'The five reasoning membership paths resolve to four contributor calls. The optional synthesis is one separately recorded reducer request, not another independent opinion.', '',
        '## Actual readiness question', '', QUESTION, '', '## Returned synthesis', '',
        outcome['synthesized_answer'] or '(No usable synthesis; read individual receipts.)', '',
        '## Evidence', '',
        'The full answers, raw task receipts, group paths, and request IDs are linked in [the JSON results](NESTED-GROUP-RESULTS.json). '
        'The readiness run is [here](group-runs/nested-readiness-20260923.json). Thirty offline tests cover the core and group implementation.', '',
        '## Use', '',
        'Open an owner-authored issue titled `SwarmBrain group: <question title>` with a JSON body: ', '',
        '```json', '{"mode":"ask","group":"reasoning","question":"Your public question","synthesize":true}', '```', '',
        'The group can be addressed again; existing peers, contexts and previous task records are retained. Child groups can also be addressed directly.', '',
        '## Scope', '', outcome['provider_note'], '',
        'Group names assign organizational roles, not separately trained specialists. Calls currently dispatch sequentially against the existing single-writer store. '
        'The collected answers retain attribution; a synthesized response is model-generated and can be wrong. '
        'The research and assurance branches contain public services and return context or checks, not simulated reasoning agents. '
        'One provider quota error was retained as a paused peer; it is excluded from the reasoning group.']
    (ROOT / 'reports/NESTED-GROUP-RESULTS.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps(outcome, indent=2))

if __name__ == '__main__': main()
