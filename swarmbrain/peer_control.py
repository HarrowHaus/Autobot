#!/usr/bin/env python3
"""Operator-dispatched peer connections, requests and task readback. One finite job."""
from __future__ import annotations
import json, os, re, sys
from pathlib import Path
from mesh import Mesh, Network, ROOT, now, write_json, normalize, digest, parts_of


def poll_task(mesh, task_id, request_id):
    """Fetch only a server-issued task ID already present in our own request history."""
    task = mesh.state['tasks'][task_id]
    remote_id = task.get('remote_task_id')
    if not remote_id:
        raise ValueError('This peer returned a direct message, not a retrievable remote task')
    peer = mesh.state['peers'][task['peer']]
    if peer.get('status') == 'paused':
        raise ValueError('Peer is paused')
    calls = mesh.state.setdefault('polls', {})
    spec_hash = digest({'task_id': task_id, 'remote_task_id': remote_id})
    if request_id in calls:
        if calls[request_id]['spec_hash'] != spec_hash:
            raise ValueError('Poll request ID belongs to a different task')
        return calls[request_id]
    method = 'tasks/get' if peer['protocol_version'].startswith('0.') else 'GetTask'
    body = {'jsonrpc': '2.0', 'id': request_id, 'method': method,
            'params': {'id': remote_id, 'historyLength': 0}}
    calls[request_id] = {'id': request_id, 'task_id': task_id, 'spec_hash': spec_hash, 'state': 'dispatching'}
    mesh.save()
    receipt = mesh.net.call(peer['endpoint'], body,
        {'A2A-Version': peer['protocol_version'], 'X-Agent-ID': 'swarmbrain-harrow'})
    path = 'reports/task-receipts/' + request_id + '.json'
    write_json(mesh.root / path, receipt)
    out = normalize(receipt, request_id)
    calls[request_id].update(at=now(), receipt=path, http_status=receipt['http_status'], state=out['state'])
    if out.get('remote_task_id') == remote_id and out['state'] in ('response_received', 'pending', 'input_required'):
        task.update(state=out['state'], remote_state=out['remote_state'], latest_poll_receipt=path, last_polled_at=now())
        calls[request_id]['remote_task_id_matched'] = True
    if receipt['http_status'] in (401, 402, 403, 429):
        peer['status'] = 'paused'
    mesh.save()
    return calls[request_id]


def render_summary(mesh, job_id, result, errors):
    mesh.save()
    summary = mesh.export()
    summary['task_count'] = summary.pop('tasks')
    summary.update(generated_at=now(), job_id=job_id, job_result=result, errors=errors,
        catalog=mesh.state.get('catalog', {}),
        directory_contacts=mesh.state.get('directory_contacts', {}),
        social_contacts=mesh.state.get('social_contacts', []),
        remote_task_polls=len(mesh.state.get('polls', {})),
        peers=[{'id': p['id'], 'name': p.get('name', p['id']), 'slot': p['slot'],
                'kind': p['kind'], 'status': p['status'], 'endpoint': p.get('endpoint'),
                'verified_results': p['verified_results']} for p in mesh.state['peers'].values()],
        tasks=list(mesh.state['tasks'].values()), background_service=False)
    write_json(mesh.root / 'reports/runtime-latest.json', summary)
    brief = ['# SwarmBrain current peer state', '', 'Generated: ' + summary['generated_at'], '',
        f"Registered peers: {summary['registered_peers']}. Connected peers: {summary['connected_peers']}. "
        f"Request records: {summary['task_count']}. Returned responses: {summary['results_received']}. "
        f"Validated task results: {summary['verified_task_results']}.", '', '## Latest job', '',
        '```json', json.dumps(result, indent=2), '```', '', '## Peer positions', '']
    brief += ['- Slot ' + str(p['slot']) + ': `' + p['id'] + '` — ' + p['status'] + '; ' + p['kind'] for p in summary['peers']]
    brief += ['', '## Interpretation', '',
        'A connected peer has returned a valid protocol response. That does not imply its every reply completes the requested task. '
        'Public services, directory agents and conversational peers are classified separately. '
        'The graph and request history persist; there is no always-running service or shared model-weight training.']
    (mesh.root / 'reports/runtime-latest.md').write_text('\n'.join(brief) + '\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in summary.items() if k not in ('tasks', 'directory_contacts', 'social_contacts')}, indent=2))
    return summary


def execute(job, job_id, root=ROOT):
    if not isinstance(job, dict) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,100}', job_id):
        raise ValueError('Expected an object and a simple stable job ID')
    mesh = Mesh(root, network=Network(max_calls=3, seconds=150))
    if 'sanctum' in mesh.state['peers']:
        mesh.state['peers']['sanctum']['kind'] = 'coordination_service'
    before_ids = {k: p['node_id'] for k, p in mesh.state['peers'].items()}
    old_tasks = set(mesh.state['tasks'])
    errors = []
    try:
        mode = job.get('mode', 'route')
        if mode == 'connect':
            peer = mesh.register(job['peer'], job['card_url'], region=job.get('region', 'general'), source='operator:' + job_id)
            connected = mesh.connect(peer['id'], job.get('protocol_version'))
            result = {'mode': mode, 'peer': peer['id'], 'card_verified': connected, 'status': peer['status']}
        elif mode == 'request':
            alias = job['peer']
            if alias not in mesh.state['peers']:
                raise ValueError('Connect this public peer first')
            payload = job.get('payload')
            if not isinstance(payload, (dict, str)) or len(json.dumps(payload)) > 12000:
                raise ValueError('Use public text or JSON of at most 12 KB')
            if alias == 'snail' and (not isinstance(payload, dict) or payload.get('operation') not in {'feed', 'thread', 'replies', 'profile'}):
                raise ValueError('Use a documented SNAIL public read operation')
            if alias == 'zenitheye' and (not isinstance(payload, dict) or payload.get('operation') not in {'arrival', 'adapter-kit'}):
                raise ValueError('Use a documented ZenithEye public read operation')
            result = mesh.send(alias, payload, job_id, depends_on=job.get('depends_on'))
        elif mode == 'poll':
            result = poll_task(mesh, job['task_id'], job_id)
        elif mode == 'route':
            result = {'routes': mesh.route(str(job.get('query', 'memory discovery')))}
        else:
            raise ValueError('Supported modes: connect, request, poll, route')
    except (ValueError, KeyError, RuntimeError, OSError) as exc:
        result = {'ok': False, 'error': str(exc)}
        errors.append({'type': type(exc).__name__, 'message': str(exc)})
    assert all(mesh.state['peers'][k]['node_id'] == v for k, v in before_ids.items())
    assert old_tasks.issubset(mesh.state['tasks'])
    mesh.state['persistence_check'] = {'prior_node_ids_preserved': len(before_ids),
        'prior_task_ids_preserved': len(old_tasks), 'checked_at': now()}
    render_summary(mesh, job_id, result, errors)
    return not errors


def main():
    event_name = os.environ.get('GITHUB_EVENT_NAME', 'local')
    if event_name == 'local':
        if len(sys.argv) != 3:
            raise SystemExit('Usage: python swarmbrain/peer_control.py job-id \'{"mode":"route","query":"memory"}\'')
        return execute(json.loads(sys.argv[2]), sys.argv[1])
    event = json.loads(Path(os.environ['GITHUB_EVENT_PATH']).read_text())
    if event_name == 'issues':
        issue = event['issue']
        if issue['user']['login'] != event['repository']['owner']['login'] or not issue['title'].startswith('SwarmBrain task:'):
            raise SystemExit('Only owner-authored SwarmBrain task issues dispatch work')
        return execute(json.loads(issue.get('body') or '{}'), 'issue-' + str(issue['number']))
    if event_name == 'workflow_dispatch':
        return execute(json.loads(event.get('inputs', {}).get('job', '{"mode":"route"}')), 'manual-' + os.environ['GITHUB_RUN_ID'])
    raise SystemExit('Unsupported event; no remote requests performed')

if __name__ == '__main__':
    raise SystemExit(0 if main() else 1)
