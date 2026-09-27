from __future__ import annotations

import os
from typing import Any

from .policy import BudgetPolicy
from .state import CommerceStore


class X402Error(RuntimeError):
    pass


def seller_app(*, handler, route: str = '/offer', price: str = '$0.01'):
    """Build a FastAPI x402 seller using the official x402 Python SDK."""
    try:
        from fastapi import FastAPI
        from x402.http import FacilitatorConfig, HTTPFacilitatorClient, PaymentOption
        from x402.http.middleware.fastapi import PaymentMiddlewareASGI
        from x402.http.types import RouteConfig
        from x402.mechanisms.evm.exact import ExactEvmServerScheme
        from x402.server import x402ResourceServer
    except ImportError as exc:
        raise X402Error('Install requirements-commerce.txt before starting the x402 seller') from exc

    pay_to = os.environ.get('SWARMBRAIN_EVM_ADDRESS')
    if not pay_to:
        raise X402Error('SWARMBRAIN_EVM_ADDRESS is required for the x402 seller')
    network = os.environ.get('SWARMBRAIN_X402_NETWORK', 'eip155:8453')
    facilitator_url = os.environ.get('SWARMBRAIN_X402_FACILITATOR', 'https://x402.org/facilitator')

    server = x402ResourceServer(HTTPFacilitatorClient(FacilitatorConfig(url=facilitator_url)))
    server.register(network, ExactEvmServerScheme())
    app = FastAPI(title='SwarmBrain x402 seller')
    routes = {
        f'GET {route}': RouteConfig(
            accepts=[PaymentOption(scheme='exact', price=price, network=network, pay_to=pay_to)]
        )
    }
    app.add_middleware(PaymentMiddlewareASGI, routes=routes, server=server)
    app.get(route)(handler)
    return app


async def paid_get(url: str, *, max_price_usd: float, purpose: str,
                   store: CommerceStore, policy: BudgetPolicy) -> dict[str, Any]:
    """Buy an x402 HTTP resource through the upstream SDK."""
    decision = policy.authorize(max_price_usd, purpose, store)
    if not decision.allowed:
        raise X402Error(decision.reason)
    private_key = os.environ.get('SWARMBRAIN_EVM_PRIVATE_KEY')
    if not private_key:
        raise X402Error('SWARMBRAIN_EVM_PRIVATE_KEY is required for x402 buying')
    try:
        from eth_account import Account
        from x402 import x402Client
        from x402.http import x402HTTPClient
        from x402.http.clients import x402HttpxClient
        from x402.mechanisms.evm import EthAccountSigner
        from x402.mechanisms.evm.exact.register import register_exact_evm_client
    except ImportError as exc:
        raise X402Error('Install requirements-commerce.txt before using x402 buying') from exc

    client = x402Client().set_spend_controls({'max_amount_per_payment': f'${float(max_price_usd):.6f}'})
    account = Account.from_key(private_key)
    register_exact_evm_client(client, EthAccountSigner(account))
    async with x402HttpxClient(client) as http:
        response = await http.get(url)
        response.raise_for_status()
        settlement = x402HTTPClient(client).get_payment_settle_response(lambda name: response.headers.get(name))
        transaction = getattr(settlement, 'transaction', None) if settlement else None
        body = response.json() if 'application/json' in response.headers.get('content-type', '') else response.text

    store.record_money(direction='out', amount_usd=max_price_usd, source='x402-cap',
                       external=True, reference=transaction, note=purpose)
    return {'url': url, 'transaction': transaction, 'body': body, 'authorized_max_usd': max_price_usd}
