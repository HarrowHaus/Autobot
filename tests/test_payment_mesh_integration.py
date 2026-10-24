"""Offline integration with the real Mesh router; all payment evidence is synthetic."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from swarmbrain import direct_usdc
from swarmbrain.mesh import Mesh, Network
from swarmbrain.payment_recovery import atomic_write
from test_payment_recovery import PAY, RPC, quote, transfer


class PaymentMeshIntegrationTests(unittest.TestCase):
    def test_paid_order_uses_real_router_without_network_or_registry_writes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            mesh = Mesh(root=root)
            mesh.state['peers']['fixture'] = dict(id='fixture', status='connected',
                capabilities=['verification'], verified_results=2, calls=3)
            mesh.save()
            registry = mesh.path.read_bytes()
            orders = root / 'orders'
            orders.mkdir()
            order = quote()
            order.update(status='expired', expired_at='preserved-original-expiry')
            path = orders / 'o1.json'
            atomic_write(path, order)
            observed = []
            def route(query, limit):
                # The route must see durable payment before it is invoked.
                saved = json.loads(path.read_text())
                self.assertEqual(saved['status'], 'paid_delivery_pending')
                self.assertEqual(saved['settlement']['verification'], 'rpc_receipt_and_canonical_block')
                observed.append(saved['quote_hash'])
                return mesh.route(query, limit)
            with patch.object(Network, 'call', side_effect=AssertionError('network forbidden')):
                result = direct_usdc.scan_orders(orders, PAY, RPC(300, [transfer()]), route)
                saved = json.loads(path.read_text())
                self.assertEqual(saved['status'], 'fulfilled')
                self.assertEqual(saved['result'][0]['peer'], 'fixture')
                self.assertEqual(saved['quote_hash'], order['quote_hash'])
                self.assertEqual(saved['expired_at'], 'preserved-original-expiry')
                self.assertEqual(len(result['fulfilled']), 1)
                second = direct_usdc.scan_orders(orders, PAY, RPC(310, [transfer()]), route)
                self.assertEqual(second['fulfilled'], [])
            self.assertEqual(len(observed), 1)
            self.assertEqual(mesh.path.read_bytes(), registry)

    def test_empty_real_router_keeps_paid_delivery_recoverable(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            mesh = Mesh(root=root)
            path = root / 'o1.json'
            atomic_write(path, quote())
            with patch.object(Network, 'call', side_effect=AssertionError('network forbidden')):
                result = direct_usdc.scan_orders(root, PAY, RPC(300, [transfer()]), mesh.route)
            saved = json.loads(path.read_text())
            self.assertEqual(saved['status'], 'paid_delivery_pending')
            self.assertIn('settlement', saved)
            self.assertNotIn('receipt_hash', saved)
            self.assertEqual(result['status'], 'degraded')
            self.assertEqual(result['review_order_ids'], ['o1'])

    def test_payment_record_survives_router_failure_and_recovers_once(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            mesh = Mesh(root=root)
            path = root / 'o1.json'
            atomic_write(path, quote())
            direct_usdc.scan_orders(root, PAY, RPC(300, [transfer()]), mesh.route)
            first = json.loads(path.read_text())
            mesh.state['peers']['fixture'] = dict(id='fixture', status='card_verified',
                capabilities=['verification'], verified_results=0, calls=0)
            result = direct_usdc.scan_orders(root, PAY, RPC(310, [transfer()]), mesh.route)
            saved = json.loads(path.read_text())
            self.assertEqual(saved['settlement'], first['settlement'])
            self.assertEqual(saved['quote_hash'], first['quote_hash'])
            self.assertEqual(saved['status'], 'fulfilled')
            self.assertEqual(len(result['fulfilled']), 1)


if __name__ == '__main__':
    unittest.main()
