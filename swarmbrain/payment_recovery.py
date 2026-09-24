"""Recover confirmed incoming payments before retiring a quote. No wallet signing.

The trusted RPC is independently checked for chain, receipt success, canonical
block, token, recipient and amount. Confirmation depth is not absolute finality.
Quote validity is never extended. Late transfers require operator review.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

CHAIN = 8453
TOKEN = '0x833589fcd6edb6e08f4c7c32d4f71b54bda02913'
TOPIC = '0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef'
CHUNK = 500
MAX_CHUNKS = 12
WARN_BLOCKS = 900
FIELDS = ('schema_version', 'order_id', 'issue_number', 'comment_id', 'requester',
          'service', 'query', 'limit', 'network', 'chain_id', 'asset', 'token_contract',
          'pay_to', 'amount_atomic', 'amount_usdc', 'from_block', 'expires_after_block',
          'confirmations', 'created_at')
TERMINAL = {'fulfilled', 'late_payment_review', 'ambiguous_payment_review'}


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def atomic_write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.'+path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as file:
            json.dump(value, file, indent=2)
            file.write('\n')
            file.flush()
            os.fsync(file.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def address(value):
    if not isinstance(value, str) or not re.fullmatch(r'0x[0-9a-fA-F]{40}', value):
        raise ValueError('invalid_address')
    return value.lower()


def validate_order(order, pay_to):
    if not isinstance(order, dict) or not re.fullmatch(r'[\w.-]{1,120}', str(order.get('order_id', ''))):
        raise ValueError('invalid_order')
    if order.get('network') != 'eip155:8453' or order.get('chain_id') != CHAIN:
        raise ValueError('wrong_order_chain')
    if address(order.get('token_contract')) != TOKEN or address(order.get('pay_to')) != address(pay_to):
        raise ValueError('wrong_asset_or_payee')
    for key in ('from_block', 'expires_after_block', 'amount_atomic', 'confirmations'):
        if type(order.get(key)) is not int or order[key] < 0:
            raise ValueError('invalid_order_integer')
    if order['confirmations'] < 5 or order['amount_atomic'] <= 0 or order['expires_after_block'] < order['from_block']:
        raise ValueError('invalid_quote_terms')
    original = {key: order[key] for key in FIELDS}
    original['status'] = 'awaiting_payment'
    if digest(original) != order.get('quote_hash'):
        raise ValueError('quote_hash_mismatch')


def verified_hit(order, log, low, high, rpc_fn):
    """No amount-only fixtures or unconfirmed/removed logs qualify."""
    try:
        block = int(log['blockNumber'], 16)
        index = int(log['logIndex'], 16)
        topics = [str(t).lower() for t in log['topics']]
        if log.get('removed') is not False or not low <= block <= high or index < 0:
            return None
        expected_to = '0x' + '0'*24 + address(order['pay_to'])[2:]
        if address(log['address']) != TOKEN or len(topics) != 3 or topics[0] != TOPIC or topics[2] != expected_to:
            return None
        if not re.fullmatch(r'0x0{24}[0-9a-f]{40}', topics[1]):
            return None
        if int(log['data'], 16) != order['amount_atomic']:
            return None
        tx = str(log['transactionHash']).lower()
        block_hash = str(log['blockHash']).lower()
        if not re.fullmatch(r'0x[0-9a-f]{64}', tx) or not re.fullmatch(r'0x[0-9a-f]{64}', block_hash):
            return None
    except (KeyError, TypeError, ValueError):
        return None
    # Transport errors propagate so a failed verification never advances the cursor.
    receipt = rpc_fn('eth_getTransactionReceipt', [tx])
    canonical = rpc_fn('eth_getBlockByNumber', [hex(block), False])
    if not isinstance(receipt, dict) or not isinstance(canonical, dict):
        raise ValueError('receipt_or_block_unavailable')
    if receipt.get('status') != '0x1' or str(receipt.get('transactionHash', '')).lower() != tx:
        return None
    if int(receipt.get('blockNumber', '-1'), 16) != block or str(receipt.get('blockHash', '')).lower() != block_hash:
        return None
    if str(canonical.get('hash', '')).lower() != block_hash:
        return None
    keys = ('address', 'topics', 'data', 'transactionHash', 'blockHash', 'blockNumber', 'logIndex')
    if not any(all(entry.get(k) == log.get(k) for k in keys) for entry in receipt.get('logs', []) if isinstance(entry, dict)):
        return None
    return {'transaction': tx, 'block_number': block, 'block_hash': block_hash,
            'log_index': index, 'event_id': f'eip155:8453:{tx}:{index}',
            'amount_atomic': order['amount_atomic'], 'payer': '0x'+topics[1][-40:],
            'verification': 'rpc_receipt_and_canonical_block', 'observed_at': now()}


def event(order, kind, detail):
    entry = {'id': digest([order['order_id'], kind]), 'order_id': order['order_id'],
             'kind': kind, 'issue_number': order['issue_number'], 'detail': detail}
    order.setdefault('recovery_events', {})[entry['id']] = entry


def deliver(order, route_fn):
    if route_fn is None:
        order['status'] = 'paid_delivery_pending'
        return
    try:
        result = route_fn(order['query'], int(order.get('limit', 3)))
        if not isinstance(result, list) or not result:
            raise ValueError('no_deliverable_routes')
        order['result'] = result
        order['fulfilled_at'] = now()
        order['status'] = 'fulfilled'
        order.pop('delivery_error', None)
        order['receipt_hash'] = digest({k: order[k] for k in ('order_id', 'quote_hash', 'settlement', 'result', 'fulfilled_at')})
        event(order, 'fulfilled', 'Confirmed incoming transfer and saved route result. Customer independence is not established by a transfer alone.')
    except Exception as error:
        order['status'] = 'paid_delivery_pending'
        order['delivery_error'] = type(error).__name__
        event(order, 'paid_delivery_pending', 'Payment is saved; fulfillment needs intervention. Do not request another payment.')


def scan_orders(orders_dir, pay_to, rpc_fn, route_fn=None, max_chunks=MAX_CHUNKS):
    rows, errors = [], []
    for path in sorted(Path(orders_dir).glob('*.json')):
        try:
            order = json.loads(path.read_text(encoding='utf-8'))
            validate_order(order, pay_to)
            rows.append((path, order))
        except Exception as error:
            errors.append({'file': path.name, 'error': type(error).__name__+': '+str(error)[:100]})
    report = {'observed_at': now(), 'fulfilled': [], 'expired': [], 'events': [],
              'errors': errors, 'orders_examined': len(rows), 'verified_external_revenue_atomic': 0}
    if not rows:
        report['status'] = 'degraded' if errors else 'ok'
        return report
    if int(rpc_fn('eth_chainId', []), 16) != CHAIN:
        raise ValueError('wrong_rpc_chain')
    latest = int(rpc_fn('eth_blockNumber', []), 16)
    report['latest_block'] = latest
    used = {o.get('settlement', {}).get('event_id') for _, o in rows}
    legacy_used_txs = {str(o.get('settlement', {}).get('transaction', '')).lower() for _, o in rows if o.get('settlement') and not o['settlement'].get('event_id')}
    rows.sort(key=lambda row: row[1].get('reconciliation', {}).get('last_scanned_block', row[1]['from_block']-1))
    remaining_chunks = 24
    for path, original in rows:
        order = copy.deepcopy(original)
        state = order.setdefault('reconciliation', {})
        try:
            if order['status'] in ('paid', 'paid_delivery_pending'):
                # Legacy paid records lack the new verification; leave those for review.
                if order.get('settlement', {}).get('verification') != 'rpc_receipt_and_canonical_block':
                    event(order, 'payment_record_review', 'Legacy payment record needs independent chain verification.')
                else:
                    saved = order['settlement']
                    receipt = rpc_fn('eth_getTransactionReceipt', [saved['transaction']])
                    log = next((entry for entry in (receipt or {}).get('logs', []) if int(entry.get('logIndex', '-1'), 16) == saved['log_index']), None)
                    checked = verified_hit(order, log or {}, order['from_block'], latest-order['confirmations'], rpc_fn)
                    if checked is None or checked['event_id'] != saved['event_id']:
                        event(order, 'payment_recheck_required', 'Previously observed transfer cannot currently be verified; hold delivery and investigate.')
                    else:
                        deliver(order, route_fn)
            elif order['status'] not in TERMINAL:
                safe = latest - order['confirmations']
                previous = state.get('last_scanned_block')
                previous_hash = state.get('last_scanned_block_hash')
                if previous is not None and previous_hash:
                    checkpoint = rpc_fn('eth_getBlockByNumber', [hex(previous), False])
                    if not isinstance(checkpoint, dict):
                        raise ValueError('checkpoint_unavailable')
                    if checkpoint.get('hash') != previous_hash:
                        state.clear()
                        event(order, 'checkpoint_reorg', 'Saved scan checkpoint changed; replaying original history before drawing conclusions.')
                low = max(order['from_block'], state.get('last_scanned_block', order['from_block']-1)+1)
                chunks = 0
                if 0 <= order['expires_after_block']-latest <= WARN_BLOCKS:
                    event(order, 'quote_deadline_near', 'Quote deadline approaching. Keep the request open; offer a new quote only when the buyer asks. Never extend a signed authorization.')
                while low <= safe and chunks < max_chunks and remaining_chunks > 0:
                    high = min(safe, low+CHUNK-1)
                    remaining_chunks -= 1
                    logs = rpc_fn('eth_getLogs', [{'address': TOKEN, 'fromBlock': hex(low), 'toBlock': hex(high),
                         'topics': [TOPIC, None, '0x'+'0'*24+address(pay_to)[2:]]}])
                    if not isinstance(logs, list):
                        raise ValueError('invalid_log_response')
                    hits = []
                    for log in logs:
                        hit = verified_hit(order, log, low, high, rpc_fn)
                        if hit and hit['event_id'] not in used and hit['transaction'] not in legacy_used_txs:
                            hits.append(hit)
                    if hits:
                        hit = sorted(hits, key=lambda h: (h['block_number'], h['log_index']))[0]
                        collisions = [o['order_id'] for _, o in rows if o['order_id'] != order['order_id'] and o['amount_atomic'] == order['amount_atomic']]
                        if len(hits) > 1 or collisions:
                            order['status'] = 'ambiguous_payment_review'
                            order['payment_candidates'] = hits
                            event(order, 'ambiguous_payment_review', 'Incoming transfer requires invoice attribution; do not count or deliver twice.')
                        else:
                            order['settlement'] = {**hit, 'confirmed_latest_block': latest}
                            used.add(hit['event_id'])
                            if hit['block_number'] > order['expires_after_block']:
                                order['status'] = 'late_payment_review'
                                event(order, 'late_payment_review', 'Transfer arrived after quote validity. Review delivery or refund; no automatic refund, recharge, or revenue claim.')
                            else:
                                order['status'] = 'paid_delivery_pending'
                                order['payment_recovered_after_expiry'] = original.get('status') == 'expired' or latest > order['expires_after_block']
                                # Commit payment BEFORE attempting delivery.
                                atomic_write(path, order)
                                deliver(order, route_fn)
                        break
                    checkpoint = rpc_fn('eth_getBlockByNumber', [hex(high), False])
                    if not isinstance(checkpoint, dict) or not re.fullmatch(r'0x[0-9a-fA-F]{64}', str(checkpoint.get('hash', ''))):
                        raise ValueError('checkpoint_unavailable')
                    state['last_scanned_block'] = high
                    state['last_scanned_block_hash'] = checkpoint['hash']
                    low = high+1
                    chunks += 1
                if order['status'] not in TERMINAL and order['status'] not in ('paid', 'paid_delivery_pending'):
                    if state.get('last_scanned_block', -1) >= order['expires_after_block']:
                        if order['status'] != 'expired':
                            report['expired'].append(order['order_id'])
                        order['status'] = 'expired'
                        order.setdefault('expired_at', now())
                        event(order, 'quote_elapsed_reconciled', 'No matching transfer found through the quote deadline. Historical monitoring remains open; this is not lost earned revenue.')
                    if low <= safe:
                        event(order, 'scan_backlog', 'Historical scan has a bounded backlog; resume at its persisted cursor. Never equate incomplete coverage with no payment.')
            if order['status'] == 'fulfilled' and original['status'] != 'fulfilled':
                report['fulfilled'].append(order)
            if order != original:
                atomic_write(path, order)
        except Exception as error:
            # Do not expire or advance the failed range; previously saved progress is intact.
            report['errors'].append({'order_id': original['order_id'], 'error': type(error).__name__})
            order = json.loads(path.read_text(encoding='utf-8'))
        report['events'].extend(order.get('recovery_events', {}).values())
    report['status'] = 'degraded' if report['errors'] else 'ok'
    return report


def cli():
    from .direct_usdc import rpc
    parser = argparse.ArgumentParser()
    parser.add_argument('--orders-dir', required=True)
    parser.add_argument('--pay-to', required=True)
    args = parser.parse_args()
    # Read-only local result selection; no transfers or authorization signing.
    from .mesh import Mesh
    mesh = Mesh()
    try:
        result = scan_orders(args.orders_dir, args.pay_to, rpc,
                             route_fn=lambda query, limit: mesh.route(query, limit=limit))
    except Exception as error:
        result = {'status': 'unavailable', 'errors': [{'error': type(error).__name__}], 'events': [], 'fulfilled': []}
    print(json.dumps(result, indent=2))
    if result['status'] != 'ok':
        raise SystemExit(1)


if __name__ == '__main__':
    cli()
