import tempfile, unittest
from pathlib import Path

import torch

from swarmbrain.real_neural_net import (
    ARCH_VERSION, FEATURE_DIM, DynamicAgentGNN, load_expandable_checkpoint,
    text_features, weighted_brier,
)


class RealNeuralNetTests(unittest.TestCase):
    def test_forward_shape(self):
        torch.manual_seed(1)
        model = DynamicAgentGNN(4, 2)
        features = torch.randn(4, FEATURE_DIM)
        edge_src = torch.tensor([0, 1, 2, 3], dtype=torch.long)
        edge_dst = torch.tensor([1, 2, 3, 0], dtype=torch.long)
        edge_rel = torch.tensor([0, 0, 1, 1], dtype=torch.long)
        edge_weight = torch.tensor([0.6, 0.7, 0.8, 0.9], dtype=torch.float32)
        h = model.encode_nodes(features, edge_src, edge_dst, edge_rel, edge_weight)
        task = torch.stack([text_features("verification"), text_features("research")])
        scores = model.score(
            h,
            torch.tensor([0, 1]),
            torch.tensor([1, 2]),
            torch.tensor([0, 1]),
            task,
            torch.tensor([0.2, 0.3]),
        )
        self.assertEqual(tuple(scores.shape), (2,))

    def test_gradient_descent_reduces_loss(self):
        torch.manual_seed(2)
        model = DynamicAgentGNN(4, 2)
        features = torch.randn(4, FEATURE_DIM)
        edge_src = torch.tensor([0, 1, 2, 3], dtype=torch.long)
        edge_dst = torch.tensor([1, 2, 3, 0], dtype=torch.long)
        edge_rel = torch.tensor([0, 0, 1, 1], dtype=torch.long)
        edge_weight = torch.tensor([0.6, 0.7, 0.8, 0.9])
        src = torch.tensor([0, 0, 1, 2])
        dst = torch.tensor([1, 2, 2, 3])
        rel = torch.tensor([0, 1, 0, 1])
        task = torch.stack([
            text_features("verification"), text_features("research"),
            text_features("verification"), text_features("code")
        ])
        prior = torch.tensor([0.3, 0.1, 0.2, 0.4])
        target = torch.tensor([1.0, 0.1, 0.9, 0.2])
        sample_weight = torch.ones(4)

        def current_loss():
            model.eval()
            with torch.no_grad():
                h = model.encode_nodes(features, edge_src, edge_dst, edge_rel, edge_weight)
                pred = torch.sigmoid(model.score(h, src, dst, rel, task, prior))
                return float(weighted_brier(pred, target, sample_weight))

        before = current_loss()
        optimizer = torch.optim.AdamW(model.parameters(), lr=0.02)
        for _ in range(80):
            model.train()
            optimizer.zero_grad(set_to_none=True)
            h = model.encode_nodes(features, edge_src, edge_dst, edge_rel, edge_weight)
            pred = torch.sigmoid(model.score(h, src, dst, rel, task, prior))
            loss = weighted_brier(pred, target, sample_weight)
            loss.backward()
            optimizer.step()
        after = current_loss()
        self.assertLess(after, before * 0.5)

    def test_expansion_preserves_old_embeddings(self):
        with tempfile.TemporaryDirectory() as d:
            checkpoint = Path(d) / "model.pt"
            torch.manual_seed(3)
            old = DynamicAgentGNN(2, 2)
            with torch.no_grad():
                old.node_embedding.weight[0].fill_(1.25)
                old.node_embedding.weight[1].fill_(2.50)
                old.relation_embedding.weight[0].fill_(3.0)
            torch.save({
                "architecture_version": ARCH_VERSION,
                "node_ids": ["a", "b"],
                "relation_ids": ["r1", "r2"],
                "state_dict": old.state_dict(),
            }, checkpoint)

            torch.manual_seed(4)
            new = DynamicAgentGNN(3, 3)
            stats = load_expandable_checkpoint(
                new, ["b", "new-agent", "a"], ["r2", "new-relation", "r1"], checkpoint
            )
            self.assertEqual(stats["reused_node_embeddings"], 2)
            self.assertEqual(stats["new_node_embeddings"], 1)
            self.assertAlmostEqual(float(new.node_embedding.weight[0, 0]), 2.50, places=5)
            self.assertAlmostEqual(float(new.node_embedding.weight[2, 0]), 1.25, places=5)
            self.assertAlmostEqual(float(new.relation_embedding.weight[2, 0]), 3.0, places=5)


if __name__ == "__main__":
    unittest.main()
