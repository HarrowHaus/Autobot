from __future__ import annotations

import os
from dataclasses import dataclass

from .state import CommerceStore


@dataclass(frozen=True)
class SpendDecision:
    allowed: bool
    reason: str
    maximum_usd: float


@dataclass(frozen=True)
class BudgetPolicy:
    operating_capital_usd: float = 20.0
    max_single_usd: float = 2.0
    max_daily_usd: float = 5.0
    minimum_reserve_usd: float = 10.0
    live_enabled: bool = False

    @classmethod
    def from_env(cls) -> 'BudgetPolicy':
        def number(name: str, default: float) -> float:
            value = float(os.environ.get(name, str(default)))
            if value < 0:
                raise ValueError(f'{name} cannot be negative')
            return value
        return cls(
            operating_capital_usd=number('SWARMBRAIN_OPERATING_CAPITAL_USD', 20.0),
            max_single_usd=number('SWARMBRAIN_MAX_SINGLE_SPEND_USD', 2.0),
            max_daily_usd=number('SWARMBRAIN_MAX_DAILY_SPEND_USD', 5.0),
            minimum_reserve_usd=number('SWARMBRAIN_MINIMUM_RESERVE_USD', 10.0),
            live_enabled=os.environ.get('SWARMBRAIN_LIVE', '').lower() in {'1', 'true', 'yes'},
        )

    def available_usd(self, store: CommerceStore) -> float:
        totals = store.totals()
        return round(self.operating_capital_usd + totals['external_revenue_usd'] - totals['spend_usd'], 6)

    def authorize(self, amount_usd: float, purpose: str, store: CommerceStore) -> SpendDecision:
        amount = float(amount_usd)
        if amount <= 0:
            return SpendDecision(False, 'Spend must be greater than zero', 0.0)
        if not self.live_enabled:
            return SpendDecision(False, 'Live spending is disabled (SWARMBRAIN_LIVE is not enabled)', 0.0)
        if amount > self.max_single_usd:
            return SpendDecision(False, f'Amount exceeds per-transaction cap of ${self.max_single_usd:.2f}', self.max_single_usd)
        daily_remaining = max(0.0, self.max_daily_usd - store.spend_on_utc_date())
        if amount > daily_remaining:
            return SpendDecision(False, f'Amount exceeds remaining daily budget of ${daily_remaining:.2f}', daily_remaining)
        reserve_limited = max(0.0, self.available_usd(store) - self.minimum_reserve_usd)
        if amount > reserve_limited:
            return SpendDecision(False, f'Amount would cross minimum reserve; spendable now is ${reserve_limited:.2f}', reserve_limited)
        if not purpose.strip():
            return SpendDecision(False, 'A concrete commercial purpose is required', 0.0)
        maximum = min(self.max_single_usd, daily_remaining, reserve_limited)
        return SpendDecision(True, f'Authorized for {purpose}', round(maximum, 6))
