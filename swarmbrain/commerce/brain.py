from __future__ import annotations

import json
import os
from typing import Any

from .acp import ACP
from .state import CommerceStore


SYSTEM_PROMPT = """You are the commercial controller for SwarmBrain.
Your objective is to increase legitimate external revenue and durable commercial relationships.
Never count transfers between our own accounts, asking prices, impressions, posts, or unsold inventory as revenue.
Use evidence before spending. Prefer cheap tests. When an opportunity produces a customer, request, objection,
referral, or adjacent need, create child opportunities so the opportunity graph grows recursively.
Do not expose private credentials, private conversations, family information, or unrelated personal files.
Do not claim an action happened unless a tool result confirms it.
"""


def build_agent(store: CommerceStore, acp: ACP):
    try:
        from deepagents import create_deep_agent
        from langchain_core.tools import tool
    except ImportError as exc:
        raise RuntimeError('Install requirements-commerce.txt to use the autonomous brain') from exc

    @tool
    def ranked_opportunities(limit: int = 10) -> str:
        """Return commercial opportunities ordered by evidence-weighted priority."""
        return json.dumps(store.ranked_opportunities(limit), indent=2)

    @tool
    def create_opportunity(title: str, hypothesis: str, parent_id: str = '',
                           estimated_margin_usd: float = 0.0, test_cost_usd: float = 0.0,
                           evidence_score: float = 0.0, novelty_score: float = 0.0) -> str:
        """Create a commercial opportunity or recursive child opportunity."""
        item = store.add_opportunity(
            title, hypothesis, parent_id=parent_id or None,
            estimated_margin_usd=estimated_margin_usd, test_cost_usd=test_cost_usd,
            evidence_score=evidence_score, novelty_score=novelty_score,
        )
        return json.dumps(item, indent=2)

    @tool
    def browse_agent_market(query: str, top_k: int = 10) -> str:
        """Search the live ACP marketplace using Virtuals' official CLI."""
        return json.dumps(acp.browse(query, top_k=top_k), indent=2)

    @tool
    def commerce_snapshot() -> str:
        """Return revenue/spend totals and object counts without credentials."""
        return json.dumps({
            'totals': store.totals(),
            'opportunities': len(store.state['opportunities']),
            'experiments': len(store.state['experiments']),
            'orders': len(store.state['orders']),
        }, indent=2)

    model = os.environ.get('SWARMBRAIN_MODEL')
    if not model:
        raise RuntimeError('Set SWARMBRAIN_MODEL to a LangChain-compatible tool-calling model')
    return create_deep_agent(
        model=model,
        tools=[ranked_opportunities, create_opportunity, browse_agent_market, commerce_snapshot],
        system_prompt=SYSTEM_PROMPT,
    )


def run_cycle(goal: str, store: CommerceStore | None = None, acp: ACP | None = None) -> dict[str, Any]:
    store = store or CommerceStore()
    acp = acp or ACP()
    agent = build_agent(store, acp)
    result = agent.invoke({'messages': goal})
    return {'result': result, 'totals': store.totals()}
