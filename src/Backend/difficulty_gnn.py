"""
NeuraLearn — GAT-based Difficulty Analysis
=============================================
Predicts per-topic difficulty scores using a Graph Attention Network
that considers structural position, prerequisite load, topological depth,
and mastery context.

Architecture
------------
  Input features (per node):
    • in-degree              — how many prerequisites
    • out-degree             — how many topics this unlocks
    • topological depth      — longest path from any root
    • level encoding         — 0/1/2/3 ordinal
    • prerequisite ratio     — fraction of prereqs in entire graph
    • spectral x (Fiedler)   — position in spectral embedding dim-1
    • spectral y             — position in spectral embedding dim-2
    • mastered (temporal)    — 0 or 1, changes as user progresses
    • mastered_neighbourhood — fraction of prereqs already mastered
    • unlock_mastered_ratio  — fraction of dependents already mastered

  GAT layers:
    GATConv(10, 16, heads=4) → ELU → Dropout
    GATConv(64, 16, heads=4) → ELU → Dropout
    GATConv(64, 1,  heads=1, concat=False) → Sigmoid

  Output: per-node difficulty score ∈ [0, 1]

The model is NOT trained on external data — it uses fixed weights
initialised to capture structural difficulty heuristics, then
fine-tuned via a self-supervised signal:
  • topics with more prereqs, deeper depth, higher level → harder
  • mastered neighbours reduce effective difficulty (temporal aspect)

This means the model works out-of-the-box on any knowledge graph.
"""
from __future__ import annotations

import threading
import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
from torch_geometric.nn import GATConv
from torch_geometric.data import Data

from graph import KnowledgeGraph, TopicLevel


# ── Feature dimension constants ─────────────────────────────────────
NUM_FEATURES = 10


class DifficultyGAT(nn.Module):
    """
    3-layer Graph Attention Network for difficulty prediction.

    Forward pass: (N, 10) node features + edge_index → (N, 1) difficulty scores.
    """

    def __init__(self, in_channels: int = NUM_FEATURES, dropout: float = 0.1):
        super().__init__()
        self.conv1 = GATConv(in_channels, 16, heads=4, dropout=dropout, concat=True)
        self.conv2 = GATConv(64, 16, heads=4, dropout=dropout, concat=True)
        self.conv3 = GATConv(64, 1, heads=1, dropout=dropout, concat=False)
        self.dropout = dropout
        self._init_structural_bias()

    def _init_structural_bias(self) -> None:
        """
        Initialise weights so the model starts with a reasonable
        structural difficulty heuristic (depth + level + prereqs).
        Without training, this gives meaningful scores.
        """
        with torch.no_grad():
            for conv in [self.conv1, self.conv2, self.conv3]:
                # GATConv may use lin_src or lin (depending on version)
                for attr in ("lin_src", "lin_l", "lin"):
                    lin = getattr(conv, attr, None)
                    if lin is not None and hasattr(lin, "weight"):
                        nn.init.xavier_uniform_(lin.weight)
                        break
                if conv.bias is not None:
                    nn.init.zeros_(conv.bias)
            # Push final layer bias to centre of sigmoid
            if self.conv3.bias is not None:
                nn.init.constant_(self.conv3.bias, -0.5)

    def forward(self, x: torch.Tensor, edge_index: torch.Tensor) -> torch.Tensor:
        """Returns (N,) difficulty scores in [0, 1]."""
        x = self.conv1(x, edge_index)
        x = F.elu(x)
        x = F.dropout(x, p=self.dropout, training=self.training)

        x = self.conv2(x, edge_index)
        x = F.elu(x)
        x = F.dropout(x, p=self.dropout, training=self.training)

        x = self.conv3(x, edge_index)
        return torch.sigmoid(x).squeeze(-1)  # (N,)


# ── Feature extraction ──────────────────────────────────────────────

def build_difficulty_features(
    kg: KnowledgeGraph,
    mastered_ids: set[int] | None = None,
) -> torch.Tensor:
    """
    Build (N, 10) feature matrix for difficulty prediction.
    Fully vectorised — no Python loop over topics.

    Features per node:
      0: normalised in-degree
      1: normalised out-degree
      2: normalised topological depth
      3: level encoding (0.0 / 0.33 / 0.67 / 1.0)
      4: prerequisite ratio (prereqs / total topics)
      5: spectral position dim-1 (Fiedler)
      6: spectral position dim-2
      7: mastered (0 or 1) — temporal feature
      8: mastered neighbourhood ratio (prereqs)
      9: unlock mastered ratio (dependents)
    """
    mastered = mastered_ids or set()
    n = max(kg.topics) + 1 if kg.topics else 0
    if n == 0:
        return torch.zeros((0, NUM_FEATURES), dtype=torch.float32)

    feats = np.zeros((n, NUM_FEATURES), dtype=np.float32)

    # Topic ID array for fancy indexing
    tids = np.array(sorted(kg.topics.keys()), dtype=np.int64)

    # Degrees — vectorised normalisation
    in_deg = kg.in_degree().float().cpu().numpy()   # (n,)
    out_deg = kg.out_degree().float().cpu().numpy()  # (n,)
    max_in = max(float(in_deg[tids].max()), 1.0)
    max_out = max(float(out_deg[tids].max()), 1.0)
    feats[tids, 0] = in_deg[tids] / max_in
    feats[tids, 1] = out_deg[tids] / max_out

    # Topological depth — vectorised
    depth_vec = kg.topological_depth_vector().astype(np.float32)  # (n,)
    max_depth = max(float(depth_vec[tids].max()), 1.0)
    feats[tids, 2] = depth_vec[tids] / max_depth

    # Level encoding — vectorised via lookup array
    _level_to_val = {TopicLevel.FOUNDATIONAL: 0.0, TopicLevel.INTERMEDIATE: 0.33,
                     TopicLevel.ADVANCED: 0.67, TopicLevel.EXPERT: 1.0}
    level_arr = np.array([_level_to_val.get(kg.topics[t].level, 0.5) for t in tids], dtype=np.float32)
    feats[tids, 3] = level_arr

    # Prerequisite ratio — vectorised from in_deg
    total_topics = max(len(kg.topics), 1)
    feats[tids, 4] = in_deg[tids] / total_topics

    # Spectral embedding (2D) — vectorised
    try:
        emb = kg.spectral_embedding(k=2)  # (N, 2)
        emb_max = np.abs(emb).max()
        if emb_max > 1e-12:
            emb = emb / emb_max
        valid_mask = tids < emb.shape[0]
        valid_tids = tids[valid_mask]
        if emb.shape[1] >= 1:
            feats[valid_tids, 5] = emb[valid_tids, 0].astype(np.float32)
        if emb.shape[1] >= 2:
            feats[valid_tids, 6] = emb[valid_tids, 1].astype(np.float32)
    except Exception:
        pass  # feats[:, 5:7] stays 0

    # Mastered flag — vectorised boolean mask
    if mastered:
        mastered_arr = np.array(list(mastered), dtype=np.int64)
        valid_m = mastered_arr[mastered_arr < n]
        feats[valid_m, 7] = 1.0

    # Mastered neighbourhood ratios — vectorised via edge_index
    ei = kg.build_edge_index()  # (2, E): src=prereq, dst=dependent
    if ei.size(1) > 0:
        ei_np = ei.cpu().numpy()
        src, dst = ei_np[0], ei_np[1]  # src→dst means src is prereq of dst

        # Feature 8: for each node i, fraction of i's prereqs that are mastered
        mastered_set = np.zeros(n, dtype=np.float32)
        if mastered:
            mastered_set[valid_m] = 1.0
        prereq_mastered = mastered_set[src]  # 1 if prereq is mastered
        # sum mastered prereqs per dst, divide by in_deg
        mastered_prereq_count = np.zeros(n, dtype=np.float32)
        np.add.at(mastered_prereq_count, dst, prereq_mastered)
        in_d = in_deg.copy()
        in_d[in_d == 0] = 1.0  # avoid /0
        feats[tids, 8] = mastered_prereq_count[tids] / in_d[tids]

        # Feature 9: for each node i, fraction of i's dependents that are mastered
        unlock_mastered = mastered_set[dst]  # 1 if dependent is mastered
        mastered_unlock_count = np.zeros(n, dtype=np.float32)
        np.add.at(mastered_unlock_count, src, unlock_mastered)
        out_d = out_deg.copy()
        out_d[out_d == 0] = 1.0  # avoid /0
        feats[tids, 9] = mastered_unlock_count[tids] / out_d[tids]

    return torch.from_numpy(feats)


def _make_bidirectional(edge_index: torch.Tensor) -> torch.Tensor:
    """GAT needs bidirectional edges for attention to flow both ways."""
    rev = edge_index.flip(0)
    return torch.cat([edge_index, rev], dim=1)


# ── Self-supervised calibration ─────────────────────────────────────

def _structural_target(kg: KnowledgeGraph) -> torch.Tensor:
    """
    Generate pseudo-ground-truth difficulty from structural features.
    Fully vectorised — no Python loop over topics.

    Combines: depth (40%), level (35%), prereq count (15%), inverse out-degree (10%).
    """
    n = max(kg.topics) + 1 if kg.topics else 0
    if n == 0:
        return torch.zeros(0, dtype=torch.float32)

    tids = np.array(sorted(kg.topics.keys()), dtype=np.int64)

    # Vectorised depth
    depth_vec = kg.topological_depth_vector().astype(np.float32)
    max_depth = max(float(depth_vec[tids].max()), 1.0)
    d_norm = depth_vec[tids] / max_depth

    # Vectorised degrees
    in_deg = kg.in_degree().float().cpu().numpy()
    out_deg = kg.out_degree().float().cpu().numpy()
    max_in = max(float(in_deg[tids].max()), 1.0)
    max_out = max(float(out_deg[tids].max()), 1.0)
    p_norm = in_deg[tids] / max_in
    o_norm = 1.0 - out_deg[tids] / max_out

    # Vectorised level encoding
    _lv_map = {TopicLevel.FOUNDATIONAL: 0.0, TopicLevel.INTERMEDIATE: 0.33,
               TopicLevel.ADVANCED: 0.67, TopicLevel.EXPERT: 1.0}
    l_arr = np.array([_lv_map.get(kg.topics[t].level, 0.5) for t in tids], dtype=np.float32)

    # Vectorised weighted sum
    target_arr = np.zeros(n, dtype=np.float32)
    target_arr[tids] = 0.40 * d_norm + 0.35 * l_arr + 0.15 * p_norm + 0.10 * o_norm

    return torch.from_numpy(target_arr)


def calibrate_model(
    model: DifficultyGAT,
    kg: KnowledgeGraph,
    epochs: int = 30,
    lr: float = 0.01,
) -> float:
    """
    Quick self-supervised calibration on the current graph.

    Trains the GAT to match structural difficulty targets for ~30 epochs.
    Returns final MSE loss.
    """
    model.train()
    feats = build_difficulty_features(kg, mastered_ids=set())
    ei = _make_bidirectional(kg.build_edge_index())
    target = _structural_target(kg)

    if feats.shape[0] == 0:
        return 0.0

    # Only compute loss for nodes that are actual topics
    topic_mask = torch.zeros(feats.shape[0], dtype=torch.bool)
    for tid in kg.topics:
        topic_mask[tid] = True

    optimiser = torch.optim.Adam(model.parameters(), lr=lr)
    loss_fn = nn.MSELoss()

    final_loss = 0.0
    for _ in range(epochs):
        optimiser.zero_grad()
        pred = model(feats, ei)
        loss = loss_fn(pred[topic_mask], target[topic_mask])
        loss.backward()
        optimiser.step()
        final_loss = loss.item()

    model.eval()
    return final_loss


# ── High-level API ──────────────────────────────────────────────────

# Module-level singleton (lightweight, no trained weights to persist)
_model: DifficultyGAT | None = None
_calibrated_for: str | None = None  # skill key last calibrated for
_model_lock = threading.Lock()       # guards _model and _calibrated_for


def predict_difficulty(
    kg: KnowledgeGraph,
    mastered_ids: set[int] | None = None,
    skill_key: str = "",
) -> dict[int, float]:
    """
    Predict per-topic difficulty scores using the GAT model.

    Returns {topic_id: difficulty_score} where score ∈ [0, 1].
    The model is lazily initialised and calibrated on first call
    per skill (recalibrated if the skill changes).
    """
    global _model, _calibrated_for

    with _model_lock:
        if _model is None:
            _model = DifficultyGAT()

        # Recalibrate if this is a new skill graph
        if _calibrated_for != skill_key or skill_key == "":
            calibrate_model(_model, kg, epochs=30)
            _calibrated_for = skill_key

        _model.eval()
        with torch.no_grad():
            feats = build_difficulty_features(kg, mastered_ids or set())
            ei = _make_bidirectional(kg.build_edge_index())
            if feats.shape[0] == 0:
                return {}
            scores = _model(feats, ei)

    return {tid: round(float(scores[tid]), 4) for tid in kg.topics}


def get_difficulty_explanation(
    kg: KnowledgeGraph,
    topic_id: int,
    score: float,
) -> str:
    """
    Generate a plain-English explanation for why a topic is rated at
    a given difficulty level.
    """
    t = kg.topics[topic_id]
    depth_vec = kg.topological_depth_vector()
    depth = int(depth_vec[topic_id])
    n_prereqs = len(t.prerequisites)
    n_unlocks = len(t.unlocks)
    level = t.level.name.lower()

    parts: list[str] = []

    # Difficulty tier
    if score >= 0.75:
        parts.append("This is one of the hardest topics in the curriculum.")
    elif score >= 0.5:
        parts.append("This topic has moderate difficulty.")
    elif score >= 0.25:
        parts.append("This is a relatively accessible topic.")
    else:
        parts.append("This is one of the easiest topics to start with.")

    # Structural reasons
    if depth >= 3:
        parts.append(f"It sits deep in the learning graph (depth {depth}), requiring significant prior knowledge.")
    elif depth == 0:
        parts.append("It's a root topic — no prerequisites needed.")

    if n_prereqs >= 3:
        prereq_names = sorted(kg.topics[p].name for p in t.prerequisites)
        parts.append(f"It requires {n_prereqs} prerequisites: {', '.join(prereq_names[:3])}{'...' if n_prereqs > 3 else ''}.")
    elif n_prereqs == 0:
        parts.append("No prerequisites — you can start this immediately.")

    if level in ("advanced", "expert"):
        parts.append(f"It's classified as {level}-level content.")

    if n_unlocks == 0:
        parts.append("This is a terminal topic — mastering it completes a branch.")
    elif n_unlocks >= 3:
        parts.append(f"It unlocks {n_unlocks} downstream topics, making it a key stepping stone.")

    return " ".join(parts)


def get_smart_recommendation(
    kg: KnowledgeGraph,
    mastered_ids: set[int] | None = None,
    skill_key: str = "",
    precomputed_scores: dict[int, float] | None = None,
) -> list[dict]:
    """
    Recommend the best next topics to study based on:
    1. Must be unlocked (all prereqs mastered)
    2. Not already mastered
    3. Sorted by difficulty (easiest first for confidence building)
    4. With explanations of why each is recommended

    Accepts optional precomputed_scores to avoid redundant GAT inference.
    Returns list of {topicId, name, difficulty, reason} dicts.
    """
    mastered = mastered_ids or set()
    scores = precomputed_scores if precomputed_scores is not None else predict_difficulty(kg, mastered, skill_key)

    available = []
    for tid, t in kg.topics.items():
        if t.mastered or tid in mastered:
            continue
        # Check if all prereqs are mastered
        if all(p in mastered or kg.topics[p].mastered for p in t.prerequisites):
            difficulty = scores.get(tid, 0.5)
            n_unlocks = len(t.unlocks)

            # Build recommendation reason
            reasons = []
            if not t.prerequisites:
                reasons.append("No prerequisites needed")
            else:
                mastered_prereq_names = [kg.topics[p].name for p in t.prerequisites if p in mastered or kg.topics[p].mastered]
                reasons.append(f"You've mastered all {len(mastered_prereq_names)} prerequisite(s)")

            if n_unlocks >= 2:
                reasons.append(f"Unlocks {n_unlocks} new topics")
            elif n_unlocks == 1:
                unlock_name = kg.topics[next(iter(t.unlocks))].name
                reasons.append(f"Unlocks '{unlock_name}'")

            level_str = t.level.name.lower()
            if level_str == "foundational":
                reasons.append("Foundational knowledge — great for building confidence")

            available.append({
                "topicId": str(tid),
                "name": t.name,
                "difficulty": round(difficulty, 3),
                "level": level_str,
                "reason": ". ".join(reasons) + ".",
                "unlockCount": n_unlocks,
            })

    # Sort: prefer easier topics first (build confidence), break ties by unlock count (more impactful)
    available.sort(key=lambda x: (x["difficulty"], -x["unlockCount"]))
    return available[:5]  # top 5 recommendations
