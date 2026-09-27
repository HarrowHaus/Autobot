from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .policy import BudgetPolicy
from .state import CommerceStore


class ACPError(RuntimeError):
    pass


class ACP:
    """Thin adapter around Virtuals' official acp CLI."""

    def __init__(self, root: str | Path | None = None, binary: str | None = None):
        self.root = Path(root or Path.cwd())
        self.binary = binary or os.environ.get('ACP_BIN') or self._discover_binary()

    def _discover_binary(self) -> str | None:
        names = ['acp.cmd', 'acp'] if os.name == 'nt' else ['acp']
        for name in names:
            local = self.root / 'node_modules' / '.bin' / name
            if local.exists():
                return str(local)
        return shutil.which('acp')

    @property
    def installed(self) -> bool:
        return bool(self.binary)

    def _run(self, args: list[str], *, timeout: int = 90) -> dict[str, Any]:
        if not self.binary:
            raise ACPError('ACP CLI is not installed. Run npm install in the repository root.')
        command = [self.binary, *args]
        if '--json' not in command:
            command.append('--json')
        proc = subprocess.run(command, cwd=self.root, text=True, capture_output=True, timeout=timeout)
        stdout, stderr = proc.stdout.strip(), proc.stderr.strip()
        if proc.returncode != 0:
            raise ACPError(stderr or stdout or f'ACP exited {proc.returncode}')
        if not stdout:
            return {'ok': True}
        try:
            return json.loads(stdout.splitlines()[-1])
        except json.JSONDecodeError as exc:
            raise ACPError(f'ACP did not return JSON: {stdout[-1000:]}') from exc

    def whoami(self) -> dict[str, Any]:
        return self._run(['agent', 'whoami'])

    def wallet_address(self) -> dict[str, Any]:
        return self._run(['wallet', 'address'])

    def wallet_balance(self, chain_id: int | None = None) -> dict[str, Any]:
        args = ['wallet', 'balance']
        if chain_id is not None:
            args += ['--chain-id', str(chain_id)]
        return self._run(args)

    def browse(self, query: str, *, top_k: int = 10, mode: str = 'mixed') -> dict[str, Any]:
        if mode not in {'relevance', 'recency', 'mixed'}:
            raise ValueError('Unsupported ACP browse mode')
        return self._run(['browse', query, '--top-k', str(top_k), '--mode', mode])

    def jobs(self) -> dict[str, Any]:
        return self._run(['job', 'list'])

    def offerings(self) -> dict[str, Any]:
        return self._run(['offering', 'list'])

    def create_offering(self, *, name: str, description: str, price_usdc: float, sla_minutes: int,
                        requirements: str, deliverable: str, live: bool) -> dict[str, Any]:
        if not live:
            return {'dry_run': True, 'command': ['acp', 'offering', 'create'], 'name': name, 'price_usdc': float(price_usdc)}
        return self._run([
            'offering', 'create', '--name', name, '--description', description,
            '--price-type', 'fixed', '--price-value', str(float(price_usdc)),
            '--sla-minutes', str(int(sla_minutes)), '--requirements', requirements,
            '--deliverable', deliverable, '--no-required-funds', '--no-hidden',
        ])

    def fund_job(self, *, job_id: str, amount_usdc: float, chain_id: int,
                 store: CommerceStore, policy: BudgetPolicy, purpose: str) -> dict[str, Any]:
        decision = policy.authorize(amount_usdc, purpose, store)
        if not decision.allowed:
            raise ACPError(decision.reason)
        result = self._run([
            'client', 'fund', '--job-id', str(job_id), '--amount', str(float(amount_usdc)),
            '--chain-id', str(chain_id),
        ])
        store.record_money(direction='out', amount_usd=amount_usdc, source='acp',
                           external=True, reference=str(job_id), note=purpose)
        return result

    def submit(self, *, job_id: str, deliverable: str, chain_id: int, live: bool) -> dict[str, Any]:
        if not live:
            return {'dry_run': True, 'job_id': job_id, 'deliverable': deliverable, 'chain_id': chain_id}
        return self._run([
            'provider', 'submit', '--job-id', str(job_id), '--deliverable', deliverable,
            '--chain-id', str(chain_id),
        ])
