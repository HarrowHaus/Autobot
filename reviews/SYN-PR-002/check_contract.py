#!/usr/bin/env python3
"""SYN-PR-002 review prototype. Offline fixtures, not external execution receipts.

The expected routes and original responses are independent inputs. This checker
validates evidence preservation, not semantic truth, provider independence,
remote exactly-once execution, or the existing SwarmBrain runtime.
"""
from __future__ import annotations
import copy
import hashlib
import json
import unittest
from typing import Any

TASK = 'SYN-PR-002-fixture'
SCOPE = hashlib.sha256(b'illustrative task input').hexdigest()
ROUTES = {
    'A': ['Research/Sources/A'],
    'Shared': ['Research/Sources/Shared', 'Research/Counterexamples/Shared'],
    'B': ['Research/Counterexamples/B'],
}
ORIGINALS = {
    'A': {'status': 'completed', 'result': 'X', 'receipt_id': 'fixture:A'},
    'Shared': {'status': 'completed', 'result': 'Y', 'receipt_id': 'fixture:Shared'},
    'B': {'status': 'timeout', 'result': None, 'receipt_id': 'fixture:B-timeout'},
}


def dispatch_plan(routes: dict[str, list[str]], task: str, scope: str) -> list[dict]:
    """One local planned dispatch per canonical identity/task/input scope.

    This pure planning function is NOT a durable dispatcher or a retry guarantee.
    Identity equivalence must already be resolved by the caller.
    """
    return [{'contributor_id': peer, 'task_id': task, 'input_scope_hash': scope,
             'paths': list(dict.fromkeys(paths))} for peer, paths in routes.items()]


def fixture() -> dict[str, Any]:
    """An explicitly synthetic example based on the task, not a remote receipt."""
    return {
        'evidence_kind': 'synthetic_regression_fixture',
        'task_id': TASK, 'input_scope_hash': SCOPE,
        'plan_paths': [p for paths in ROUTES.values() for p in paths],
        'contributions': {peer: {
            'contributor_id': peer, 'paths': list(paths),
            'input_scope_hash': SCOPE, **copy.deepcopy(ORIGINALS[peer]),
            'outcome_unknown': ORIGINALS[peer]['status'] != 'completed',
        } for peer, paths in ROUTES.items()},
        'synthesis': {
            'counts_as_contribution': False, 'consensus': 'not_established',
            'summary_result': None, 'source_contributors': ['A', 'Shared'],
            'disagreements': [{
                'contributor_ids': ['A', 'Shared'],
                'evidence_receipt_ids': ['fixture:A', 'fixture:Shared'],
                'basis': 'task_stipulation', 'review_status': 'unreviewed',
            }],
        },
    }


def check(value: dict, routes: dict, originals: dict,
          task: str, scope: str) -> list[str]:
    """Return violations against independent expected routes and originals.

    This deliberately limited, single-task/single-input-scope review contract
    does not support partial response streams. Comparisons are structural.
    JSON null may be a valid completed result when present in the original.
    """
    errors: list[str] = []
    def require(condition: bool, message: str) -> None:
        if not condition:
            errors.append(message)
    if not isinstance(value, dict):
        return ['result is not an object']
    require(value.get('task_id') == task, 'task identity changed')
    require(value.get('input_scope_hash') == scope, 'input scope changed')
    expected = [p for paths in routes.values() for p in paths]
    supplied = value.get('plan_paths')
    require(isinstance(supplied, list) and all(isinstance(p, str) for p in supplied)
            and sorted(supplied) == sorted(expected), 'plan paths changed')
    contributions = value.get('contributions')
    if not isinstance(contributions, dict):
        return errors + ['contributions missing or invalid']
    require(set(contributions) == set(routes), 'missing or extra canonical contributor')
    for peer, paths in routes.items():
        item = contributions.get(peer)
        if not isinstance(item, dict):
            errors.append(peer + ': contribution missing or invalid')
            continue
        require(item.get('contributor_id') == peer, peer + ': identity changed')
        require(item.get('input_scope_hash') == scope, peer + ': scope changed')
        actual = item.get('paths')
        require(isinstance(actual, list) and all(isinstance(p, str) for p in actual)
                and sorted(actual) == sorted(paths), peer + ': paths changed')
        for field in ('status', 'result', 'receipt_id'):
            require(field in item and item[field] == originals[peer][field],
                    peer + ': original ' + field + ' changed')
        if originals[peer]['status'] != 'completed':
            require(item.get('outcome_unknown') is True, peer + ': unknown outcome hidden')
    synthesis = value.get('synthesis')
    if not isinstance(synthesis, dict):
        return errors + ['synthesis missing or invalid']
    require(synthesis.get('counts_as_contribution') is False, 'synthesis counted as evidence')
    # This prototype deliberately never certifies consensus from unreviewed responses.
    require(synthesis.get('consensus') == 'not_established', 'unreviewed consensus asserted')
    require('summary_result' in synthesis and synthesis['summary_result'] is None,
            'unreviewed combined result asserted')
    sources = synthesis.get('source_contributors')
    successful = {p for p, original in originals.items() if original['status'] == 'completed'}
    require(isinstance(sources, list) and all(isinstance(p, str) for p in sources)
            and len(sources) == len(set(sources)) and set(sources) <= successful,
            'invalid or duplicate synthesis source')
    disputes = synthesis.get('disagreements')
    if not isinstance(disputes, list):
        return errors + ['disagreements missing or invalid']
    for dispute in disputes:
        if not isinstance(dispute, dict):
            errors.append('invalid disagreement')
            continue
        peers = dispute.get('contributor_ids')
        if not (isinstance(peers, list) and all(isinstance(p, str) for p in peers)
                and len(peers) >= 2 and len(peers) == len(set(peers))
                and set(peers) <= successful):
            errors.append('disagreement has unknown or incomplete contributor')
            continue
        require(dispute.get('evidence_receipt_ids') == [originals[p]['receipt_id'] for p in peers],
                'disagreement evidence changed')
        require(dispute.get('basis') in ('task_stipulation', 'attributed_review'),
                'string inequality is not a semantic disagreement finding')
        require(dispute.get('review_status') == 'unreviewed', 'review status inflated')
    # The task stipulates this specific conflict, independently of generated prose.
    if originals == ORIGINALS:
        require(any(isinstance(d, dict) and d.get('contributor_ids') == ['A', 'Shared']
                    for d in disputes), 'stipulated conflict omitted')
    return errors


class ContractTests(unittest.TestCase):
    def assert_valid(self, value: dict) -> None:
        self.assertEqual(check(value, ROUTES, ORIGINALS, TASK, SCOPE), [])

    def assert_rejected(self, value: dict) -> None:
        self.assertTrue(check(value, ROUTES, ORIGINALS, TASK, SCOPE))

    def test_shared_two_paths_one_planned_dispatch_and_contribution(self) -> None:
        plan = dispatch_plan(ROUTES, TASK, SCOPE)
        shared = [p for p in plan if p['contributor_id'] == 'Shared']
        self.assertEqual(len(plan), 3)
        self.assertEqual(len(shared), 1)
        self.assertEqual(shared[0]['paths'], ROUTES['Shared'])
        self.assert_valid(fixture())
        duplicate = fixture()
        duplicate['contributions']['Shared-copy'] = copy.deepcopy(duplicate['contributions']['Shared'])
        self.assert_rejected(duplicate)

    def test_timeout_conflict_and_separate_synthesis(self) -> None:
        value = fixture()
        self.assert_valid(value)
        for field, bad in (('consensus', 'established'), ('counts_as_contribution', True),
                           ('summary_result', 'X'), ('source_contributors', ['A', 'Shared', 'B']),
                           ('source_contributors', ['A', 'Shared', 'Shared']), ('disagreements', [])):
            with self.subTest(field=field, bad=bad):
                altered = copy.deepcopy(value)
                altered['synthesis'][field] = bad
                self.assert_rejected(altered)
        value['contributions']['B']['outcome_unknown'] = False
        self.assert_rejected(value)
        value = fixture()
        value['synthesis']['disagreements'][0]['basis'] = 'string_inequality'
        self.assert_rejected(value)

    def test_missing_path_or_original_fails_despite_reassuring_summary(self) -> None:
        for mutation in ('path', 'plan_and_path', 'original', 'receipt', 'missing_result',
                         'unknown_status', 'scope', 'missing_contributor', 'wrong_identity'):
            with self.subTest(mutation=mutation):
                value = fixture()
                value['synthesis']['prose'] = 'All paths and original answers are preserved.'
                shared = value['contributions']['Shared']
                if mutation in ('path', 'plan_and_path'):
                    shared['paths'].pop()
                if mutation == 'plan_and_path':
                    value['plan_paths'].remove('Research/Counterexamples/Shared')
                if mutation == 'original': shared['result'] = 'X'
                if mutation == 'receipt': shared['receipt_id'] = 'fixture:forged'
                if mutation == 'missing_result': shared.pop('result')
                if mutation == 'unknown_status': shared['status'] = 'verified'
                if mutation == 'scope': shared['input_scope_hash'] = 'different'
                if mutation == 'missing_contributor': value['contributions'].pop('Shared')
                if mutation == 'wrong_identity': shared['contributor_id'] = 'B'
                self.assert_rejected(value)


if __name__ == '__main__':
    unittest.main(verbosity=2)
