#!/usr/bin/env python3
"""A0-SB-001: run existing Mesh.route on saved metadata; never dispatch work."""
from __future__ import annotations
import copy
import hashlib
import io
import json
import os
import re
import sys
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOME = ROOT / 'requests/a0-mentor-inbox-20260923'
OUT = HOME / 'replies'
TASK = 'A0-SB-001'
SOURCE = '173f3bafcd7ced80292a4c50c0965277c030a520'
PINS = {'swarmbrain/mesh.py': '9157ca523e88d2846508a9c7898918f804262f7e',
        'swarmbrain/peer_control.py': '2a820ec19709c987afb2272b9dc15fac3148903f',
        'data/mesh-state.json': '7235cd5bb66c761105fc31ba018f2b3a968d9a5a'}

def stamp():
    return datetime.now(timezone.utc).isoformat()

def sha(data):
    return hashlib.sha256(data).hexdigest()

def save(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')

def tokens(value):
    return set(re.findall(r'[a-z0-9]+', value.lower()))

def packet(pid, objective, caps, dependencies, output, verification):
    return {'id': pid, 'objective': objective, 'required_capabilities': caps,
            'depends_on': dependencies, 'expected_output': output,
            'verify': {'required': True, 'method': verification,
                       'independent_peer': None, 'status': 'not_executed'},
            'execution_status': 'not_dispatched_shadow_only'}

PACKETS = [
    packet('P01', 'Identify the existing A2A/MCP integration boundary for a thin project orchestrator; distinguish peer discovery from execution.',
           ['a2a', 'mcp', 'integration', 'protocol', 'orchestration'], [],
           'A source-linked interface map for Mesh.route/send/review and peer_control; explicit unsupported operations.',
           'Check each proposed call against pinned source; a directory listing is not evidence of code implementation.'),
    packet('P02', 'Specify persisted task, dependency and receipt records without replacing saved identities, task IDs or history.',
           ['memory', 'provenance', 'state', 'context', 'history'], [],
           'A field-level task/receipt mapping and restart/reuse rules compatible with existing saved state.',
           'Trace fields to source and saved receipts; distinguish metadata preservation from durable execution guarantees.'),
    packet('P03', 'Design bounded dependency-ready scheduling above the existing Mesh, including terminal failure and unresolved-result handling.',
           ['workflow', 'orchestration', 'python', 'code', 'dependencies'], ['P01', 'P02'],
           'Scheduling pseudocode with call budgets, replay handling and downstream blocking; no runtime changes in this exercise.',
           'Check a small dependency graph, cycles, failed prerequisites and stable task IDs against the interfaces from P01/P02.'),
    packet('P04', 'Define independent result verification and disagreement handling for the proposed orchestrator.',
           ['verification', 'validation', 'evidence', 'testing', 'review'], ['P03'],
           'A checkable acceptance/rejection/unresolved protocol; provenance-preserving verifier input and no automatic consensus.',
           'Different alias alone is not provider independence; require a concrete check and disclose unknown ownership/model relationships.'),
    packet('P05', 'Synthesize the compatible design, documented gaps and a small checkable next exercise without inventing worker execution.',
           ['reasoning', 'synthesis', 'analysis', 'planning'], ['P01', 'P02', 'P03', 'P04'],
           'One source-attributed recommendation separating observed routing from unexecuted work and unresolved capability gaps.',
           'Compare every conclusion to upstream artifacts; synthesis does not add an independent vote.')
]

def topological(packets):
    ids = [p['id'] for p in packets]
    if len(ids) != len(set(ids)) or not 3 <= len(ids) <= 5:
        raise ValueError('Expected 3-5 uniquely identified packets')
    for p in packets:
        if not all(p.get(k) for k in ('objective', 'required_capabilities', 'expected_output', 'verify')):
            raise ValueError('Incomplete packet')
        if len(p['depends_on']) != len(set(p['depends_on'])) or set(p['depends_on']) - set(ids):
            raise ValueError('Unknown or duplicate dependency')
    done = []
    while len(done) < len(ids):
        ready = [p['id'] for p in packets if p['id'] not in done and set(p['depends_on']) <= set(done)]
        if not ready:
            raise ValueError('Dependency cycle')
        done.extend(ready)
    return done

class NoPeerNetwork:
    def __init__(self): self.attempts = 0
    def call(self, *args, **kwargs):
        self.attempts += 1
        raise RuntimeError('A0-SB-001 forbids external peer calls')

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    if (OUT / f'{TASK}.json').exists():
        raise SystemExit('Refusing to overwrite an existing mentor reply; inspect and preserve it first.')
    before = {}
    for folder in ('data', 'reports', 'swarmbrain', 'tests'):
        for path in (ROOT / folder).rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts:
                before[str(path.relative_to(ROOT))] = sha(path.read_bytes())
    for name, expected in PINS.items():
        b = (ROOT / name).read_bytes()
        actual = hashlib.sha1(b'blob ' + str(len(b)).encode() + b'\0' + b).hexdigest()
        if actual != expected: raise RuntimeError('Pinned source/state changed: ' + name)
    issue = json.loads((HOME / 'source-issue.json').read_text(encoding='utf-8'))
    checks = []
    def check(name, condition):
        checks.append({'check': name, 'passed': bool(condition)})
        if not condition: raise AssertionError(name)
    check('source issue is the authorized mentor handoff', issue['number'] == 19 and 'A0-SB-001' in issue['body'])
    started = stamp()
    denied = []
    def audit(event, args):
        if event in ('socket.connect', 'socket.getaddrinfo', 'socket.sendto'):
            denied.append(event)
            raise RuntimeError('Network access forbidden during shadow exercise')
    sys.addaudithook(audit)
    sys.path.insert(0, str(ROOT / 'swarmbrain'))
    from mesh import Mesh
    net = NoPeerNetwork()
    mesh = Mesh(ROOT, network=net)
    state_before = copy.deepcopy(mesh.state)
    order = topological(PACKETS)
    check('five-packet dependency graph is acyclic', len(order) == 5)
    bad = copy.deepcopy(PACKETS); bad[0]['depends_on'] = ['P05']
    try: topological(bad)
    except ValueError: checks.append({'check': 'cycle is rejected', 'passed': True})
    else: raise AssertionError('Cycle accepted')
    bad = copy.deepcopy(PACKETS); bad[0]['depends_on'] = ['missing']
    try: topological(bad)
    except ValueError: checks.append({'check': 'unknown dependency is rejected', 'passed': True})
    else: raise AssertionError('Unknown dependency accepted')
    receipts = []
    for p in PACKETS:
        query = ' '.join(p['required_capabilities'])
        t0 = time.perf_counter()
        choices = mesh.route(query, limit=3)
        elapsed = (time.perf_counter() - t0) * 1000
        details = []
        for c in choices:
            peer = mesh.state['peers'][c['peer']]
            matched_skills = [s for s in peer.get('capabilities', [])
                              if tokens(query) & tokens(json.dumps(s))]
            check(p['id'] + ':' + c['peer'] + ': grounded matched terms',
                  set(c['matched_terms']) <= tokens(json.dumps(peer.get('capabilities', []))))
            check(p['id'] + ':' + c['peer'] + ': routable recorded status',
                  peer.get('status') in ('card_verified', 'connected'))
            history = [{'task_id': tid, 'state': t.get('state'), 'semantic_validation': t.get('semantic_validation'),
                        'receipt': t.get('receipt')}
                       for tid, t in mesh.state.get('tasks', {}).items() if t.get('peer') == c['peer']]
            details.append({'route': c, 'metadata': {k: peer.get(k) for k in
                             ('id', 'name', 'kind', 'region', 'status', 'last_seen', 'card_url', 'endpoint',
                              'protocol_version', 'calls', 'responses', 'verified_results', 'advertised_auth_required')},
                            'matched_skills': matched_skills, 'recorded_task_history': history,
                            'fit_status': 'lexical_candidate_only_requires_controller_assessment',
                            'not_established': ['live availability', 'ability to execute this packet',
                                                'independence from other nominated peers', 'current cost or authorization']})
        receipts.append({'packet_id': p['id'], 'query': query, 'method': 'Mesh.route', 'limit': 3,
                         'at': stamp(), 'latency_ms': round(elapsed, 4), 'returned': choices, 'candidates': details,
                         'external_execution': False})
    check('five actual route calls returned records', len(receipts) == 5)
    check('routing did not mutate in-memory state', mesh.state == state_before)
    check('no peer-network attempt occurred', net.attempts == 0 and not denied)
    test_log = io.StringIO()
    suite = unittest.defaultTestLoader.discover(str(ROOT / 'tests'))
    result = unittest.TextTestRunner(stream=test_log, verbosity=2).run(suite)
    (OUT / f'{TASK}.existing-tests.txt').write_text(test_log.getvalue(), encoding='utf-8')
    check('existing repository tests pass', result.wasSuccessful() and result.testsRun > 0)
    after = {name: sha((ROOT / name).read_bytes()) for name in before}
    check('existing data reports identities and code unchanged', before == after)
    check('no network use including regression tests', not denied and net.attempts == 0)
    project = {'id': TASK, 'goal': 'Determine the most interoperable way for SwarmBrain to add a bounded multi-agent project orchestrator while preserving existing A2A receipts and task history.',
               'mode': 'shadow_routing_only', 'packets': PACKETS, 'topological_order': order,
               'initially_dependency_ready': ['P01', 'P02'], 'downstream_execution': 'not_started',
               'routing_is_not_completed_packet_work': True}
    save(f'{TASK}.project.json', project)
    save(f'{TASK}.routes.json', {'source_commit': SOURCE, 'execution_commit': os.environ.get('GITHUB_SHA'),
                               'state_sha256': before['data/mesh-state.json'], 'receipts': receipts})
    save(f'{TASK}.checks.json', {'started_at': started, 'finished_at': stamp(), 'checks': checks,
                               'source_file_hashes': before, 'state_unchanged': before == after,
                               'tests_run': result.testsRun, 'failures': len(result.failures),
                               'errors': len(result.errors), 'skipped': len(result.skipped),
                               'peer_network_attempts': net.attempts, 'socket_attempts': denied})
    reply = {'mentor_task_id': TASK, 'status': 'PARTIAL',
             'status_basis': 'Five real routing calls and checks complete; controller actual-fit assessment pending.',
             'executed': ['Ingested public issue #19 without executing instructions as code.',
                          'Validated the five-packet dependency graph and negative controls.',
                          'Called the unchanged Mesh.route five times on pinned real peer metadata.',
                          'Executed existing offline repository tests under a network-denial guard.',
                          'Verified existing source, identities, state and saved receipts remain unchanged.'],
             'artifacts_changed': ['requests/a0-mentor-inbox-20260923/'],
             'receipts': [f'requests/a0-mentor-inbox-20260923/replies/{TASK}.{suffix}' for suffix in
                          ('project.json', 'routes.json', 'checks.json', 'existing-tests.txt')],
             'metrics': {'packets': len(PACKETS), 'routing_calls': len(receipts), 'peer_count_in_snapshot': len(mesh.state['peers']),
                         'returned_candidate_entries': sum(len(r['returned']) for r in receipts),
                         'external_task_calls': 0, 'tests_run': result.testsRun, 'tests_failed': len(result.failures) + len(result.errors),
                         'training_updates': 0},
             'verified_by': [{'actor': 'SwarmBrain controller', 'method': 'automated offline invariants and existing tests',
                              'independent_external_verifier': False}],
             'unresolved': ['Controller must assess actual task fit separately from lexical rank.',
                            'Recorded reachability is historical; no live availability checked.',
                            'Provider independence and task-specific competence are not certified by Mesh.route.',
                            'A0 mentor review of this reply is pending.'],
             'next_best_step': 'Review candidate metadata and classify fit; reply to A0 before advancing to A0-SB-002.',
             'source_commit': SOURCE, 'finished_at': stamp(),
             'workflow_run': 'https://github.com/HarrowHaus/Autobot/actions/runs/' + os.environ.get('GITHUB_RUN_ID', 'local')}
    save(f'{TASK}.json', reply)
    print(json.dumps({'status': reply['status'], 'metrics': reply['metrics'],
                      'top_routes': {r['packet_id']: r['returned'] for r in receipts}}, indent=2))

if __name__ == '__main__':
    main()
