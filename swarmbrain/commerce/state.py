from __future__ import annotations

import json
import os
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z')


def default_state_path() -> Path:
    configured = os.environ.get('SWARMBRAIN_COMMERCE_STATE')
    if configured:
        return Path(configured).expanduser()
    return Path.home() / '.swarmbrain' / 'commerce-state.json'


class CommerceStore:
    """Private local commercial memory. The default lives outside the repo."""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path).expanduser() if path else default_state_path()
        self.state = self._load()

    @staticmethod
    def empty() -> dict[str, Any]:
        now = utc_now()
        return {
            'schema_version': 1,
            'created_at': now,
            'updated_at': now,
            'opportunities': {},
            'experiments': {},
            'orders': {},
            'ledger': [],
            'relationships': {},
        }

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return self.empty()
        data = json.loads(self.path.read_text(encoding='utf-8'))
        if data.get('schema_version') != 1:
            raise ValueError('Unsupported commerce state schema')
        for key in ('opportunities', 'experiments', 'orders', 'ledger', 'relationships'):
            if key not in data:
                raise ValueError(f'Commerce state missing {key}')
        return data

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.state['updated_at'] = utc_now()
        payload = json.dumps(self.state, indent=2, sort_keys=True) + '\n'
        fd, tmp = tempfile.mkstemp(prefix=self.path.name + '.', dir=str(self.path.parent))
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)

    @staticmethod
    def _unit(value: float) -> float:
        return round(max(0.0, min(1.0, float(value))), 6)

    @staticmethod
    def priority(item: dict[str, Any]) -> float:
        margin = max(0.0, float(item.get('estimated_margin_usd', 0.0)))
        cost = max(0.0, float(item.get('test_cost_usd', 0.0)))
        evidence = max(0.0, min(1.0, float(item.get('evidence_score', 0.0))))
        novelty = max(0.0, min(1.0, float(item.get('novelty_score', 0.0))))
        return round(((margin + 1.0) * (0.65 + evidence)) / (cost + 1.0) + 0.2 * novelty, 6)

    def add_opportunity(
        self,
        title: str,
        hypothesis: str,
        *,
        evidence: list[dict[str, Any]] | None = None,
        parent_id: str | None = None,
        estimated_margin_usd: float = 0.0,
        test_cost_usd: float = 0.0,
        evidence_score: float = 0.0,
        novelty_score: float = 0.0,
    ) -> dict[str, Any]:
        if parent_id and parent_id not in self.state['opportunities']:
            raise ValueError('Unknown parent opportunity')
        oid = 'opp-' + uuid.uuid4().hex[:12]
        item = {
            'id': oid,
            'title': title.strip(),
            'hypothesis': hypothesis.strip(),
            'parent_id': parent_id,
            'created_at': utc_now(),
            'status': 'candidate',
            'evidence': evidence or [],
            'estimated_margin_usd': round(float(estimated_margin_usd), 6),
            'test_cost_usd': round(float(test_cost_usd), 6),
            'evidence_score': self._unit(evidence_score),
            'novelty_score': self._unit(novelty_score),
        }
        item['priority'] = self.priority(item)
        self.state['opportunities'][oid] = item
        self.save()
        return item

    def ranked_opportunities(self, limit: int = 10) -> list[dict[str, Any]]:
        active = [
            value for value in self.state['opportunities'].values()
            if value.get('status') not in {'closed', 'rejected'}
        ]
        for item in active:
            item['priority'] = self.priority(item)
        return sorted(active, key=lambda x: (-x['priority'], x['created_at']))[:max(1, limit)]

    def record_experiment(self, opportunity_id: str, hypothesis: str, max_cost_usd: float) -> dict[str, Any]:
        if opportunity_id not in self.state['opportunities']:
            raise ValueError('Unknown opportunity')
        eid = 'exp-' + uuid.uuid4().hex[:12]
        item = {
            'id': eid,
            'opportunity_id': opportunity_id,
            'hypothesis': hypothesis.strip(),
            'max_cost_usd': round(float(max_cost_usd), 6),
            'created_at': utc_now(),
            'status': 'planned',
            'observations': [],
        }
        self.state['experiments'][eid] = item
        self.save()
        return item

    def add_observation(self, experiment_id: str, observation: dict[str, Any]) -> dict[str, Any]:
        item = self.state['experiments'][experiment_id]
        item['observations'].append({'at': utc_now(), **observation})
        item['status'] = 'running'
        self.save()
        return item

    def record_order(self, order_id: str, *, source: str, status: str, gross_usd: float = 0.0, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        if order_id in self.state['orders']:
            existing = self.state['orders'][order_id]
            if source != existing['source']:
                raise ValueError('Order ID already belongs to another source')
            existing.update(status=status, gross_usd=round(float(gross_usd), 6), updated_at=utc_now())
            if metadata:
                existing.setdefault('metadata', {}).update(metadata)
            self.save()
            return existing
        item = {
            'id': order_id,
            'source': source,
            'status': status,
            'gross_usd': round(float(gross_usd), 6),
            'created_at': utc_now(),
            'updated_at': utc_now(),
            'metadata': metadata or {},
        }
        self.state['orders'][order_id] = item
        self.save()
        return item

    def record_money(
        self,
        *,
        direction: str,
        amount_usd: float,
        source: str,
        external: bool,
        reference: str | None = None,
        note: str | None = None,
    ) -> dict[str, Any]:
        if direction not in {'in', 'out'}:
            raise ValueError('direction must be in or out')
        amount = round(float(amount_usd), 6)
        if amount < 0:
            raise ValueError('amount_usd must be non-negative')
        item = {
            'id': 'money-' + uuid.uuid4().hex[:12],
            'at': utc_now(),
            'direction': direction,
            'amount_usd': amount,
            'source': source,
            'external': bool(external),
            'reference': reference,
            'note': note,
        }
        self.state['ledger'].append(item)
        self.save()
        return item

    def totals(self) -> dict[str, float]:
        incoming = sum(x['amount_usd'] for x in self.state['ledger'] if x['direction'] == 'in' and x['external'])
        outgoing = sum(x['amount_usd'] for x in self.state['ledger'] if x['direction'] == 'out')
        internal_incoming = sum(x['amount_usd'] for x in self.state['ledger'] if x['direction'] == 'in' and not x['external'])
        return {
            'external_revenue_usd': round(incoming, 6),
            'spend_usd': round(outgoing, 6),
            'internal_transfers_in_usd': round(internal_incoming, 6),
            'net_external_usd': round(incoming - outgoing, 6),
        }

    def spend_on_utc_date(self, date_text: str | None = None) -> float:
        target = date_text or datetime.now(timezone.utc).date().isoformat()
        return round(sum(
            x['amount_usd'] for x in self.state['ledger']
            if x['direction'] == 'out' and x['at'][:10] == target
        ), 6)
