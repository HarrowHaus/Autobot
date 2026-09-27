#!/usr/bin/env python3
"""Train and query the actual SwarmBrain graph neural network.

The ledger/event log is evidence. This module creates trainable parameters,
uses backpropagation, persists a checkpoint, expands its embedding table when
new agent/node IDs appear, and scores future interactions.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import random
from pathlib import Path
from typing import Any

import torch
from torch import nn
import torch.nn.functional as F

ROOT = Path(__file__).resolve().parents[1]
LEDGER_PATH = ROOT / "data" / "agent-ledger.json"
SYNAPSE_PATH = ROOT / "data" / "agent-synapses.json"
EVENT_PATH = ROOT / "reports" / "agent-interactions.ndjson"
MODEL_DIR = ROOT / "data" / "neural"
CHECKPOINT_PATH = MODEL_DIR / "swarmbrain_gnn.pt"
INDEX_PATH = MODEL_DIR / "model-index.json"
TRAINING_REPORT = ROOT / "reports" / "neural-training-latest.json"
ROUTING_REPORT = ROOT / "reports" / "neural-routing-latest.json"

ARCH_VERSION = 1
FEATURE_HASH_BINS = 48
NUMERIC_FEATURES = 8
FEATURE_DIM = FEATURE_HASH_BINS + NUMERIC_FEATURES
TASK_DIM = 64
HIDDEN_DIM = 48
REL_DIM = 16
EMBED_DIM = HIDDEN_DIM
DEFAULT_EPOCHS = 30
DEFAULT_LR = 0.004

NON_AGENT_KINDS = {"public_coordination_thread", "invalid_identity_marker"}

TARGET_BY_EVENT = {
    "observed": 0.25,
    "mention": 0.30,
    "conversation": 0.38,
    "referral": 0.62,
    "task_sent": 0.55,
    "task_accepted": 0.72,
    "task_result": 0.90,
    "result_validated": 1.00,
    "capability_verified": 0.82,
    "failure": 0.05,
    "decline": 0.18,
}
WEIGHT_BY_EVENT = {
    "observed": 0.4,
    "mention": 0.5,
    "conversation": 0.35,
    "referral": 1.5,
    "task_sent": 1.2,
    "task_accepted": 1.8,
    "task_result": 3.0,
    "result_validated": 4.0,
    "capability_verified": 2.0,
    "failure": 3.0,
    "decline": 1.5,
}

COMMON_RELATIONS = [
    "conversation", "public_thread_interaction", "referral", "task_sent",
    "task.accepted", "task.result", "task.error", "result_validated",
    "card_observed", "knows",
]


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def stable_bucket(text: str, size: int) -> tuple[int, float]:
    raw = hashlib.blake2b(text.encode("utf-8"), digest_size=8).digest()
    value = int.from_bytes(raw, "big")
    idx = value % size
    sign = 1.0 if (value >> 8) & 1 else -1.0
    return idx, sign


def add_hashed(vec: torch.Tensor, token: str, scale: float = 1.0) -> None:
    idx, sign = stable_bucket(token, FEATURE_HASH_BINS)
    vec[idx] += sign * scale


def text_features(text: str) -> torch.Tensor:
    import re
    vec = torch.zeros(TASK_DIM, dtype=torch.float32)
    tokens = [t for t in re.findall(r"[a-z0-9][a-z0-9._:/+-]*", (text or "").lower()) if len(t) > 1]
    for tok in tokens[:256]:
        idx, sign = stable_bucket("task:" + tok, TASK_DIM)
        vec[idx] += sign
    norm = torch.linalg.vector_norm(vec)
    if norm > 0:
        vec /= norm
    return vec


def node_features(agent: dict[str, Any]) -> torch.Tensor:
    vec = torch.zeros(FEATURE_DIM, dtype=torch.float32)
    tokens: list[tuple[str, float]] = []
    for key in ("kind", "status", "catalog_state"):
        val = agent.get(key)
        if val:
            tokens.append((f"{key}:{val}", 1.0))
    for p in agent.get("provenance", [])[:12]:
        tokens.append((f"prov:{p}", 0.8))
    for alias in agent.get("aliases", [])[:12]:
        tokens.append((f"alias:{str(alias).lower()}", 0.3))
    for interface in agent.get("interfaces", [])[:12]:
        if not isinstance(interface, dict):
            continue
        kind = interface.get("kind")
        if kind:
            tokens.append((f"iface:{kind}", 0.6))
        url = interface.get("url")
        if isinstance(url, str) and "://" in url:
            try:
                host = url.split("://", 1)[1].split("/", 1)[0].lower()
                tokens.append((f"host:{host}", 0.5))
            except Exception:
                pass
    caps = []
    for key in ("capabilities_observed", "capabilities_advertised"):
        value = agent.get(key, [])
        if isinstance(value, list):
            caps.extend(value[:32])
    for cap in caps:
        if isinstance(cap, dict):
            for key in ("id", "name"):
                if cap.get(key):
                    tokens.append((f"cap:{str(cap[key]).lower()}", 0.9))
            for tag in cap.get("tags", [])[:12]:
                tokens.append((f"tag:{str(tag).lower()}", 0.7))
        elif isinstance(cap, str):
            tokens.append((f"cap:{cap.lower()}", 0.8))
    for token, scale in tokens:
        add_hashed(vec, token, scale)

    base = FEATURE_HASH_BINS
    vec[base + 0] = math.log1p(float(agent.get("interaction_count", 0))) / 8.0
    vec[base + 1] = math.log1p(float(agent.get("validated_result_count", 0))) / 4.0
    vec[base + 2] = math.log1p(float(agent.get("referrals_given", 0))) / 4.0
    vec[base + 3] = math.log1p(float(agent.get("referrals_received", 0))) / 4.0
    vec[base + 4] = min(1.0, len(agent.get("interfaces", [])) / 8.0)
    vec[base + 5] = 1.0 if agent.get("status") in ("active", "connected", "reachable", "card_verified") else 0.0
    vec[base + 6] = 1.0 if agent.get("kind") == "coordinator" else 0.0
    vec[base + 7] = 1.0 if agent.get("card_live") is True else 0.0
    return vec


def load_events() -> list[dict[str, Any]]:
    if not EVENT_PATH.exists():
        return []
    out = []
    with EVENT_PATH.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(item, dict):
                out.append(item)
    return out


def build_task_outcomes(events: list[dict[str, Any]]) -> dict[str, float]:
    grouped: dict[str, list[str]] = {}
    for e in events:
        env = e.get("runtime_envelope") or {}
        task_id = env.get("task_id")
        if task_id:
            grouped.setdefault(str(task_id), []).append(str(e.get("event_type") or ""))
    result = {}
    for task_id, kinds in grouped.items():
        if "result_validated" in kinds:
            result[task_id] = 1.0
        elif "task_result" in kinds:
            result[task_id] = 0.95
        elif "failure" in kinds:
            result[task_id] = 0.05
        elif "task_accepted" in kinds:
            result[task_id] = 0.70
        else:
            result[task_id] = 0.50
    return result


class DynamicAgentGNN(nn.Module):
    def __init__(self, n_nodes: int, n_relations: int):
        super().__init__()
        self.node_embedding = nn.Embedding(n_nodes, EMBED_DIM)
        self.feature_proj = nn.Linear(FEATURE_DIM, HIDDEN_DIM)
        self.relation_embedding = nn.Embedding(n_relations, REL_DIM)
        self.relation_to_hidden = nn.Linear(REL_DIM, HIDDEN_DIM, bias=False)
        self.conv1_self = nn.Linear(HIDDEN_DIM, HIDDEN_DIM)
        self.conv1_neigh = nn.Linear(HIDDEN_DIM, HIDDEN_DIM)
        self.conv2_self = nn.Linear(HIDDEN_DIM, HIDDEN_DIM)
        self.conv2_neigh = nn.Linear(HIDDEN_DIM, HIDDEN_DIM)
        self.task_encoder = nn.Sequential(
            nn.Linear(TASK_DIM, HIDDEN_DIM),
            nn.ReLU(),
            nn.Linear(HIDDEN_DIM, HIDDEN_DIM),
        )
        self.scorer = nn.Sequential(
            nn.Linear(HIDDEN_DIM * 3 + REL_DIM + 1, HIDDEN_DIM),
            nn.ReLU(),
            nn.Linear(HIDDEN_DIM, 1),
        )
        self.reset_parameters()

    def reset_parameters(self):
        nn.init.normal_(self.node_embedding.weight, mean=0.0, std=0.08)
        nn.init.normal_(self.relation_embedding.weight, mean=0.0, std=0.08)

    def encode_nodes(
        self,
        features: torch.Tensor,
        edge_src: torch.Tensor,
        edge_dst: torch.Tensor,
        edge_rel: torch.Tensor,
        edge_weight: torch.Tensor,
    ) -> torch.Tensor:
        h = torch.tanh(self.feature_proj(features) + self.node_embedding.weight)
        if edge_src.numel() == 0:
            return F.relu(self.conv2_self(F.relu(self.conv1_self(h))))

        rel_h = self.relation_to_hidden(self.relation_embedding(edge_rel))

        def propagate(current: torch.Tensor, self_layer: nn.Linear, neigh_layer: nn.Linear) -> torch.Tensor:
            weighted = torch.clamp(edge_weight, min=0.0, max=1.0).unsqueeze(1)
            msg = (current[edge_src] + rel_h) * weighted
            agg = torch.zeros_like(current)
            agg.index_add_(0, edge_dst, msg)
            deg = torch.zeros(current.shape[0], dtype=current.dtype, device=current.device)
            deg.index_add_(0, edge_dst, weighted.squeeze(1))
            agg = agg / deg.clamp_min(1.0).unsqueeze(1)
            return F.relu(self_layer(current) + neigh_layer(agg))

        h = propagate(h, self.conv1_self, self.conv1_neigh)
        h = propagate(h, self.conv2_self, self.conv2_neigh)
        return h

    def score(
        self,
        node_repr: torch.Tensor,
        src: torch.Tensor,
        dst: torch.Tensor,
        rel: torch.Tensor,
        task: torch.Tensor,
        prior_edge_weight: torch.Tensor,
    ) -> torch.Tensor:
        task_h = self.task_encoder(task)
        rel_h = self.relation_embedding(rel)
        x = torch.cat(
            [
                node_repr[src],
                node_repr[dst],
                task_h,
                rel_h,
                prior_edge_weight.unsqueeze(1),
            ],
            dim=1,
        )
        return self.scorer(x).squeeze(1)


def prepare_graph():
    ledger = load_json(LEDGER_PATH, {"agents": {}})
    synapses = load_json(SYNAPSE_PATH, {"edges": {}})
    agents = ledger.get("agents", {})
    node_ids = sorted(agents)
    if not node_ids:
        raise RuntimeError("agent ledger is empty")
    node_index = {aid: i for i, aid in enumerate(node_ids)}
    features = torch.stack([node_features(agents[aid]) for aid in node_ids])

    relations = set(COMMON_RELATIONS)
    events = load_events()
    for edge in synapses.get("edges", {}).values():
        if isinstance(edge, dict) and edge.get("relation"):
            relations.add(str(edge["relation"]))
    for e in events:
        if e.get("relation"):
            relations.add(str(e["relation"]))
        elif e.get("event_type"):
            relations.add(str(e["event_type"]))
    relation_ids = sorted(relations)
    rel_index = {r: i for i, r in enumerate(relation_ids)}

    srcs, dsts, rels, weights = [], [], [], []
    edge_prior: dict[tuple[str, str, str], float] = {}
    for edge in synapses.get("edges", {}).values():
        if not isinstance(edge, dict):
            continue
        s, d = edge.get("source"), edge.get("target")
        if s not in node_index or d not in node_index:
            continue
        relation = str(edge.get("relation") or "conversation")
        weight = float(edge.get("weight", 0.0))
        norm = math.log1p(max(0.0, weight)) / math.log(101.0)
        srcs.append(node_index[s])
        dsts.append(node_index[d])
        rels.append(rel_index[relation])
        weights.append(norm)
        edge_prior[(s, d, relation)] = norm

    edge_src = torch.tensor(srcs, dtype=torch.long)
    edge_dst = torch.tensor(dsts, dtype=torch.long)
    edge_rel = torch.tensor(rels, dtype=torch.long)
    edge_weight = torch.tensor(weights, dtype=torch.float32)
    return ledger, agents, node_ids, node_index, relation_ids, rel_index, features, edge_src, edge_dst, edge_rel, edge_weight, edge_prior, events


def prepare_samples(node_index, rel_index, edge_prior, events):
    task_outcomes = build_task_outcomes(events)
    samples = []
    for e in events:
        s, d = e.get("source_agent"), e.get("target_agent")
        if s not in node_index or d not in node_index:
            continue
        event_type = str(e.get("event_type") or "observed")
        relation = str(e.get("relation") or event_type)
        if relation not in rel_index:
            continue
        target = TARGET_BY_EVENT.get(event_type, 0.32)
        env = e.get("runtime_envelope") or {}
        task_id = env.get("task_id")
        if event_type == "task_sent" and task_id and str(task_id) in task_outcomes:
            target = task_outcomes[str(task_id)]
        weight = WEIGHT_BY_EVENT.get(event_type, 0.5)
        text = str(e.get("body_excerpt") or "")
        event_id = str(e.get("event_id") or f"{s}:{d}:{len(samples)}")
        prior = edge_prior.get((s, d, relation), 0.0)
        samples.append(
            {
                "event_id": event_id,
                "src": node_index[s],
                "dst": node_index[d],
                "rel": rel_index[relation],
                "task": text_features(text),
                "prior": prior,
                "target": float(target),
                "weight": float(weight),
                "type": event_type,
            }
        )
    if not samples:
        raise RuntimeError("no trainable interaction samples")
    return samples


def split_samples(samples):
    train, holdout = [], []
    for sample in samples:
        h = int(hashlib.sha256(sample["event_id"].encode()).hexdigest()[:8], 16)
        (holdout if h % 5 == 0 else train).append(sample)
    if not train:
        train = samples[:]
    if not holdout:
        holdout = samples[-max(1, len(samples) // 5):]
    return train, holdout


def batch_tensors(samples):
    return (
        torch.tensor([s["src"] for s in samples], dtype=torch.long),
        torch.tensor([s["dst"] for s in samples], dtype=torch.long),
        torch.tensor([s["rel"] for s in samples], dtype=torch.long),
        torch.stack([s["task"] for s in samples]),
        torch.tensor([s["prior"] for s in samples], dtype=torch.float32),
        torch.tensor([s["target"] for s in samples], dtype=torch.float32),
        torch.tensor([s["weight"] for s in samples], dtype=torch.float32),
    )


def weighted_brier(pred, target, weight):
    return ((pred - target).pow(2) * weight).sum() / weight.sum().clamp_min(1e-6)


def load_expandable_checkpoint(model, node_ids, relation_ids, path=CHECKPOINT_PATH):
    stats = {
        "checkpoint_found": False,
        "reused_node_embeddings": 0,
        "new_node_embeddings": len(node_ids),
        "reused_relation_embeddings": 0,
        "new_relation_embeddings": len(relation_ids),
    }
    if not path.exists():
        return stats
    checkpoint = torch.load(path, map_location="cpu", weights_only=False)
    if checkpoint.get("architecture_version") != ARCH_VERSION:
        return stats
    stats["checkpoint_found"] = True
    old_state = checkpoint.get("state_dict", {})
    current = model.state_dict()
    for key, value in old_state.items():
        if key in ("node_embedding.weight", "relation_embedding.weight"):
            continue
        if key in current and tuple(current[key].shape) == tuple(value.shape):
            current[key].copy_(value)
    model.load_state_dict(current)

    old_nodes = checkpoint.get("node_ids", [])
    old_relations = checkpoint.get("relation_ids", [])
    old_node_weight = old_state.get("node_embedding.weight")
    old_rel_weight = old_state.get("relation_embedding.weight")
    with torch.no_grad():
        if old_node_weight is not None:
            old_map = {x: i for i, x in enumerate(old_nodes)}
            for new_i, node_id in enumerate(node_ids):
                old_i = old_map.get(node_id)
                if old_i is not None and old_i < old_node_weight.shape[0]:
                    model.node_embedding.weight[new_i].copy_(old_node_weight[old_i])
                    stats["reused_node_embeddings"] += 1
        if old_rel_weight is not None:
            old_map = {x: i for i, x in enumerate(old_relations)}
            for new_i, rel_id in enumerate(relation_ids):
                old_i = old_map.get(rel_id)
                if old_i is not None and old_i < old_rel_weight.shape[0]:
                    model.relation_embedding.weight[new_i].copy_(old_rel_weight[old_i])
                    stats["reused_relation_embeddings"] += 1
    stats["new_node_embeddings"] = len(node_ids) - stats["reused_node_embeddings"]
    stats["new_relation_embeddings"] = len(relation_ids) - stats["reused_relation_embeddings"]
    return stats


def evaluate(model, graph_tensors, samples):
    if not samples:
        return {"loss": None, "mae": None, "count": 0}
    features, edge_src, edge_dst, edge_rel, edge_weight = graph_tensors
    model.eval()
    with torch.no_grad():
        h = model.encode_nodes(features, edge_src, edge_dst, edge_rel, edge_weight)
        src, dst, rel, task, prior, target, weight = batch_tensors(samples)
        pred = torch.sigmoid(model.score(h, src, dst, rel, task, prior))
        return {
            "loss": float(weighted_brier(pred, target, weight).item()),
            "mae": float(torch.mean(torch.abs(pred - target)).item()),
            "count": len(samples),
            "prediction_mean": float(pred.mean().item()),
            "target_mean": float(target.mean().item()),
        }


def train_model(epochs=DEFAULT_EPOCHS, lr=DEFAULT_LR, seed=7):
    random.seed(seed)
    torch.manual_seed(seed)
    (
        ledger, agents, node_ids, node_index, relation_ids, rel_index,
        features, edge_src, edge_dst, edge_rel, edge_weight, edge_prior, events
    ) = prepare_graph()
    samples = prepare_samples(node_index, rel_index, edge_prior, events)
    train, holdout = split_samples(samples)
    model = DynamicAgentGNN(len(node_ids), len(relation_ids))
    expansion = load_expandable_checkpoint(model, node_ids, relation_ids)
    graph_tensors = (features, edge_src, edge_dst, edge_rel, edge_weight)
    before = evaluate(model, graph_tensors, holdout)
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    src, dst, rel, task, prior, target, sample_weight = batch_tensors(train)

    history = []
    for _ in range(max(1, int(epochs))):
        model.train()
        optimizer.zero_grad(set_to_none=True)
        h = model.encode_nodes(features, edge_src, edge_dst, edge_rel, edge_weight)
        pred = torch.sigmoid(model.score(h, src, dst, rel, task, prior))
        loss = weighted_brier(pred, target, sample_weight)
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 2.0)
        optimizer.step()
        history.append(float(loss.item()))

    after_train = evaluate(model, graph_tensors, train)
    after_holdout = evaluate(model, graph_tensors, holdout)
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    checkpoint = {
        "architecture_version": ARCH_VERSION,
        "node_ids": node_ids,
        "relation_ids": relation_ids,
        "state_dict": model.state_dict(),
        "feature_dim": FEATURE_DIM,
        "task_dim": TASK_DIM,
        "hidden_dim": HIDDEN_DIM,
        "relation_dim": REL_DIM,
    }
    torch.save(checkpoint, CHECKPOINT_PATH)
    index = {
        "architecture_version": ARCH_VERSION,
        "node_ids": node_ids,
        "relation_ids": relation_ids,
        "checkpoint": str(CHECKPOINT_PATH.relative_to(ROOT)),
    }
    INDEX_PATH.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")
    parameter_count = sum(p.numel() for p in model.parameters())
    report = {
        "architecture": "DynamicAgentGNN",
        "architecture_version": ARCH_VERSION,
        "framework": f"PyTorch {torch.__version__}",
        "real_backpropagation": True,
        "optimizer": "AdamW",
        "epochs": int(epochs),
        "learning_rate": float(lr),
        "parameter_count": int(parameter_count),
        "trainable_parameter_count": int(sum(p.numel() for p in model.parameters() if p.requires_grad)),
        "node_count": len(node_ids),
        "agent_count": sum(agents[aid].get("kind") not in NON_AGENT_KINDS for aid in node_ids),
        "relation_count": len(relation_ids),
        "edge_count": int(edge_src.numel()),
        "sample_count": len(samples),
        "train_count": len(train),
        "holdout_count": len(holdout),
        "expansion": expansion,
        "initial_holdout": before,
        "final_train": after_train,
        "final_holdout": after_holdout,
        "train_loss_first": history[0] if history else None,
        "train_loss_last": history[-1] if history else None,
        "checkpoint": str(CHECKPOINT_PATH.relative_to(ROOT)),
        "model_index": str(INDEX_PATH.relative_to(ROOT)),
    }
    TRAINING_REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def load_model_for_inference():
    (
        ledger, agents, node_ids, node_index, relation_ids, rel_index,
        features, edge_src, edge_dst, edge_rel, edge_weight, edge_prior, events
    ) = prepare_graph()
    if not CHECKPOINT_PATH.exists():
        raise RuntimeError("neural checkpoint does not exist; train first")
    model = DynamicAgentGNN(len(node_ids), len(relation_ids))
    stats = load_expandable_checkpoint(model, node_ids, relation_ids)
    if not stats["checkpoint_found"]:
        raise RuntimeError("checkpoint architecture incompatible")
    model.eval()
    with torch.no_grad():
        h = model.encode_nodes(features, edge_src, edge_dst, edge_rel, edge_weight)
    return model, h, ledger, agents, node_ids, node_index, relation_ids, rel_index, edge_prior


def neural_scores(query: str, candidate_ids: list[str], source_id: str = "agent:rook", relation: str = "task_sent") -> dict[str, float]:
    model, h, ledger, agents, node_ids, node_index, relation_ids, rel_index, edge_prior = load_model_for_inference()
    if source_id not in node_index:
        raise KeyError(f"unknown source {source_id}")
    rel_name = relation if relation in rel_index else "task_sent"
    rel_id = rel_index[rel_name]
    task = text_features(query)
    valid = [aid for aid in candidate_ids if aid in node_index]
    if not valid:
        return {}
    src = torch.full((len(valid),), node_index[source_id], dtype=torch.long)
    dst = torch.tensor([node_index[aid] for aid in valid], dtype=torch.long)
    rel = torch.full((len(valid),), rel_id, dtype=torch.long)
    task_batch = task.unsqueeze(0).repeat(len(valid), 1)
    prior = torch.tensor([edge_prior.get((source_id, aid, rel_name), 0.0) for aid in valid], dtype=torch.float32)
    with torch.no_grad():
        scores = torch.sigmoid(model.score(h, src, dst, rel, task_batch, prior))
    return {aid: float(score) for aid, score in zip(valid, scores.tolist())}


def resolve_candidate_ids(agents: dict[str, Any], names: list[str]) -> dict[str, str]:
    lookup = {}
    for aid, agent in agents.items():
        values = [agent.get("name"), *agent.get("aliases", [])]
        for value in values:
            if value:
                lookup.setdefault(str(value).strip().lower(), aid)
    return {name: lookup.get(name.strip().lower(), "") for name in names}


def neural_scores_for_names(query: str, names: list[str], source_id: str = "agent:rook", relation: str = "task_sent") -> dict[str, float]:
    model, h, ledger, agents, node_ids, node_index, relation_ids, rel_index, edge_prior = load_model_for_inference()
    if source_id not in node_index:
        return {}
    mapping = resolve_candidate_ids(agents, names)
    rel_name = relation if relation in rel_index else "task_sent"
    rel_id = rel_index[rel_name]
    task = text_features(query)
    valid = [(name, aid) for name, aid in mapping.items() if aid and aid in node_index]
    if not valid:
        return {}
    src = torch.full((len(valid),), node_index[source_id], dtype=torch.long)
    dst = torch.tensor([node_index[aid] for _, aid in valid], dtype=torch.long)
    rel = torch.full((len(valid),), rel_id, dtype=torch.long)
    task_batch = task.unsqueeze(0).repeat(len(valid), 1)
    prior = torch.tensor([edge_prior.get((source_id, aid, rel_name), 0.0) for _, aid in valid], dtype=torch.float32)
    with torch.no_grad():
        scores = torch.sigmoid(model.score(h, src, dst, rel, task_batch, prior))
    return {name: float(score) for (name, _), score in zip(valid, scores.tolist())}


def rank_candidates(query: str, top_k: int = 20, source_id: str = "agent:rook", relation: str = "task_sent"):
    model, h, ledger, agents, node_ids, node_index, relation_ids, rel_index, edge_prior = load_model_for_inference()
    candidates = [
        aid for aid in node_ids
        if aid != source_id
        and agents[aid].get("kind") not in NON_AGENT_KINDS
        and agents[aid].get("status") != "retracted"
    ]
    scores = neural_scores(query, candidates, source_id=source_id, relation=relation)
    rows = []
    for aid, score in scores.items():
        agent = agents[aid]
        rows.append({
            "agent_id": aid,
            "name": agent.get("name") or aid,
            "aliases": agent.get("aliases", []),
            "kind": agent.get("kind"),
            "status": agent.get("status"),
            "neural_score": round(score, 6),
            "interaction_count": agent.get("interaction_count", 0),
            "validated_result_count": agent.get("validated_result_count", 0),
        })
    rows.sort(key=lambda x: (-x["neural_score"], -x["validated_result_count"], -x["interaction_count"], x["agent_id"]))
    result = {
        "query_sha256": hashlib.sha256(query.encode()).hexdigest(),
        "source_id": source_id,
        "relation": relation,
        "top_k": min(top_k, len(rows)),
        "results": rows[:max(1, top_k)],
    }
    ROUTING_REPORT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="command", required=True)
    train = sub.add_parser("train")
    train.add_argument("--epochs", type=int, default=DEFAULT_EPOCHS)
    train.add_argument("--lr", type=float, default=DEFAULT_LR)
    train.add_argument("--seed", type=int, default=7)
    route = sub.add_parser("route")
    route.add_argument("query")
    route.add_argument("--top-k", type=int, default=20)
    route.add_argument("--source", default="agent:rook")
    route.add_argument("--relation", default="task_sent")
    args = ap.parse_args()
    if args.command == "train":
        out = train_model(args.epochs, args.lr, args.seed)
    else:
        out = rank_candidates(args.query, args.top_k, args.source, args.relation)
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    main()
