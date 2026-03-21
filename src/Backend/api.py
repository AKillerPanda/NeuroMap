"""
NeuraLearn — Flask REST API  (spectral layout + vectorised + full feature surface)
===================================================================================
Exposes the backend algorithms (Webscraping, KnowledgeGraph, ACO, SDS)
as JSON endpoints that the React frontend can consume.

Layout uses spectral graph embedding (Laplacian eigenvectors) for natural
node positioning, falling back to topological-depth layers when the graph
is too small for meaningful spectral analysis.

Endpoints
---------
POST /api/generate       — Build knowledge graph + learning paths for a skill
POST /api/spell-check    — SDS spell-correction for a word / phrase
POST /api/sub-graph      — Generate a sub-graph for a specific subtopic
POST /api/master         — Mark a topic as mastered (prerequisite-validated)
POST /api/shortest-path  — Shortest path to a target topic
GET  /api/progress/<skill> — Get mastery progress for a stored graph
GET  /api/health         — Health check
"""
from __future__ import annotations

import difflib
import logging
import math
import os
import re
import time
import traceback
import threading
import weakref
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from itertools import combinations
from typing import Any
from urllib.parse import quote

import numpy as np
from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_compress import Compress
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# ── Backend imports ─────────────────────────────────────────────────
from Webscraping import get_learning_spec
from graph import KnowledgeGraph, TopicLevel
from SDS import spell_correct, correct_phrase, load_dictionary
from ACO import LearningPathACO, ParallelLearningACO
# difficulty_gnn imports torch eagerly — defer to first use
_predict_difficulty = None
_get_difficulty_explanation = None
_get_smart_recommendation = None

def _ensure_difficulty_gnn():
    global _predict_difficulty, _get_difficulty_explanation, _get_smart_recommendation
    if _predict_difficulty is None:
        try:
            from difficulty_gnn import predict_difficulty, get_difficulty_explanation, get_smart_recommendation
            _predict_difficulty = predict_difficulty
            _get_difficulty_explanation = get_difficulty_explanation
            _get_smart_recommendation = get_smart_recommendation
        except Exception as exc:
            log.warning("difficulty_gnn unavailable; using heuristic fallback: %s", exc)

            def _fallback_predict(kg: KnowledgeGraph, mastered_ids: set[int] | None = None, **_: Any) -> dict[int, float]:
                level_to_score = {
                    "foundational": 0.2,
                    "intermediate": 0.5,
                    "advanced": 0.75,
                    "expert": 0.9,
                }
                mastered_ids = mastered_ids or set()
                scores: dict[int, float] = {}
                for tid, topic in kg.topics.items():
                    level_str = topic.level.name.lower() if hasattr(topic.level, "name") else str(topic.level)
                    base = level_to_score.get(level_str, 0.5)
                    scores[tid] = 0.05 if tid in mastered_ids else base
                return scores

            def _fallback_explanation(_: KnowledgeGraph, __: int, score: float) -> str:
                return (
                    "AI difficulty model is unavailable in this environment, "
                    f"so a heuristic score ({score:.2f}) based on topic level is shown."
                )

            def _fallback_recommendation(
                kg: KnowledgeGraph,
                mastered_ids: set[int] | None = None,
                precomputed_scores: dict[int, float] | None = None,
                **_: Any,
            ) -> list[dict[str, Any]]:
                mastered_ids = mastered_ids or set()
                scores = precomputed_scores or _fallback_predict(kg, mastered_ids)
                available = [t for t in kg.get_available() if t.topic_id not in mastered_ids]
                available.sort(key=lambda t: scores.get(t.topic_id, 0.5))
                return [
                    {
                        "topicId": t.topic_id,
                        "name": t.name,
                        "difficulty": scores.get(t.topic_id, 0.5),
                        "reason": "Recommended from prerequisite-ready topics.",
                    }
                    for t in available
                ]

            _predict_difficulty = _fallback_predict
            _get_difficulty_explanation = _fallback_explanation
            _get_smart_recommendation = _fallback_recommendation

# ── App setup ───────────────────────────────────────────────────────
app = Flask(__name__)
CORS(app)  # allow requests from the Vite dev server

# Enable response compression for all responses > 1KB
Compress(app)

# Configure for production
app.config['JSON_SORT_KEYS'] = False
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = os.getenv('FLASK_ENV', 'production') != 'production'

# Add security headers middleware
@app.after_request
def add_security_headers(response):
    """Add security headers to all responses."""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    response.headers['Cache-Control'] = 'public, max-age=3600'
    return response

logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s")
log = logging.getLogger(__name__)

# Pre-load the dictionary on startup so /spell-check is fast
_dict = load_dictionary()
log.info("Dictionary loaded: %d words", len(_dict))

# In-memory graph store: skill (lowercased) → (KnowledgeGraph, spec_list)
# Keeps graphs alive for mastery tracking & shortest-path queries.
# Uses OrderedDict with LRU eviction to cap memory at _GRAPH_STORE_MAX entries.
_GRAPH_STORE_MAX = 50
_graph_store: OrderedDict[str, tuple[KnowledgeGraph, list[dict]]] = OrderedDict()
_graph_lock = threading.Lock()
# Per-skill mutation locks: prevent concurrent master_topic() calls corrupting one KG
_kg_locks: dict[str, threading.Lock] = {}
_kg_locks_lock = threading.Lock()

def _get_kg_lock(key: str) -> threading.Lock:
    """Return (creating if necessary) the per-graph mutation lock for `key`."""
    with _kg_locks_lock:
        if key not in _kg_locks:
            _kg_locks[key] = threading.Lock()
        return _kg_locks[key]

def _store_graph(key: str, value: tuple[KnowledgeGraph, list[dict]]) -> None:
    """Thread-safe LRU insert into the graph store."""
    with _graph_lock:
        if key in _graph_store:
            _graph_store.move_to_end(key)
        _graph_store[key] = value
        while len(_graph_store) > _GRAPH_STORE_MAX:
            evicted_key, _ = _graph_store.popitem(last=False)
            # Clean up the associated lock to prevent unbounded growth
            with _kg_locks_lock:
                _kg_locks.pop(evicted_key, None)

def _get_graph(key: str) -> tuple[KnowledgeGraph, list[dict]] | None:
    """Thread-safe LRU lookup."""
    with _graph_lock:
        entry = _graph_store.get(key)
        if entry is not None:
            _graph_store.move_to_end(key)
        return entry


# ═══════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════
_LEVEL_TO_DIFFICULTY: dict[str, str] = {
    "foundational": "beginner",
    "intermediate": "intermediate",
    "advanced":     "advanced",
    "expert":       "advanced",
}

_LEVEL_ORDER = ["foundational", "intermediate", "advanced", "expert"]

# Study time estimates in minutes per topic by difficulty level
_STUDY_TIME_MINUTES: dict[str, int] = {
    "foundational": 45,
    "intermediate": 90,
    "advanced":     150,
    "expert":       210,
}


def _layout_nodes(kg: KnowledgeGraph, spec: list[dict] | None = None) -> list[dict[str, Any]]:
    """
    Sugiyama-style layered layout with spectral cross-minimisation.

    1. Y-axis  — topological depth layers (vectorised BFS).
    2. X-axis  — *within* each layer, order nodes to minimise edge crossings
       via barycenter heuristic (average x of parents), seeded with spectral
       Fiedler ordering for the root layer.
    3. Spacing — enforce a hard minimum gap (NODE_W) so nodes never overlap
       regardless of how many share a layer.

    Also attaches:
      - spectral cluster label for colour-coding
      - learning resources from the scrape spec

    The result is a clean, readable DAG where every level is evenly spaced,
    edges flow strictly downward, and no two nodes collide.
    """
    topo = kg.learning_order()
    if not topo:
        return []

    # O(1) step-index lookup (avoids O(n²) topo.index())
    topo_idx: dict[int, int] = {t.topic_id: i for i, t in enumerate(topo)}

    # ── constants ───────────────────────────────────────────────────
    NODE_W   = 260          # min horizontal gap (> node width ~220 px)
    Y_GAP    = 160          # vertical gap between layers
    CENTER_X = 500          # viewport centre-x

    # ── depth vector ────────────────────────────────────────────────
    depth_vec = kg.topological_depth_vector()          # (N,) int32
    max_depth = int(depth_vec[list(kg.topics.keys())].max()) if kg.topics else 0

    # ── group topics by layer ───────────────────────────────────────
    layers: dict[int, list] = {}
    for t in topo:
        d = int(depth_vec[t.topic_id])
        layers.setdefault(d, []).append(t)

    # ── spectral seed for the root layer ────────────────────────────
    spectral_order: dict[int, float] = {}
    if kg.num_topics >= 3:
        try:
            fiedler = kg.fiedler_vector()
            fv_max = float(np.abs(fiedler).max())
            if fv_max > 1e-12:
                for tid in kg.topics:
                    spectral_order[tid] = float(fiedler[tid]) / fv_max
        except Exception:
            pass

    # ── barycenter cross-minimisation (two passes) ──────────────────
    # Assign each topic a fractional x-rank within its layer.
    # Roots are ordered by Fiedler value; deeper layers by the mean
    # x-rank of their parents (barycenter heuristic — Sugiyama §3).
    layer_rank: dict[int, float] = {}   # topic_id → x-rank (0-based float)

    for d in range(max_depth + 1):
        lt = layers.get(d, [])
        if not lt:
            continue
        if d == 0:
            # Root layer: prefer spectral order, else alphabetical
            lt.sort(key=lambda t: spectral_order.get(t.topic_id, 0.0))
        else:
            # Barycenter: average rank of already-placed parents
            def _bary(t):
                parents = [layer_rank[p] for p in t.prerequisites if p in layer_rank]
                return sum(parents) / len(parents) if parents else 0.0
            lt.sort(key=_bary)
        for i, t in enumerate(lt):
            layer_rank[t.topic_id] = float(i)

    # 2nd pass (bottom-up refinement) — reduces remaining crossings
    for d in range(max_depth, -1, -1):
        lt = layers.get(d, [])
        if not lt:
            continue
        def _child_bary(t):
            children = [layer_rank[u] for u in t.unlocks if u in layer_rank]
            return sum(children) / len(children) if children else layer_rank.get(t.topic_id, 0.0)
        lt.sort(key=_child_bary)
        for i, t in enumerate(lt):
            layer_rank[t.topic_id] = float(i)

    # ── absolute pixel positions (centred, no-overlap) ──────────────
    # Pre-compute spectral cluster labels for colour-coding
    cluster_map: dict[int, int] = {}
    if kg.num_topics >= 3:
        try:
            n_clust = max(2, min(kg.num_topics // 3, 5))
            labels = kg.spectral_clustering(n_clusters=n_clust)
            for tid in kg.topics:
                cluster_map[tid] = int(labels[tid])
        except Exception:
            pass

    # Build resource lookup: lowercase topic name → list of resource dicts
    resource_map: dict[str, list[dict]] = {}
    if spec:
        for s in spec:
            key = s.get("name", "").lower()
            resource_map[key] = s.get("resources", [])

    nodes: list[dict[str, Any]] = []
    for d in range(max_depth + 1):
        lt = layers.get(d, [])
        if not lt:
            continue
        n = len(lt)
        total_w = (n - 1) * NODE_W
        start_x = CENTER_X - total_w / 2
        for i, t in enumerate(lt):
            level_str = t.level.name.lower() if hasattr(t.level, "name") else str(t.level)
            node_type = "input" if d == 0 else ("output" if d == max_depth else "default")

            # Contextual metadata for the frontend
            prereq_names = sorted(kg.topics[p].name for p in t.prerequisites)
            unlock_names = sorted(kg.topics[u].name for u in t.unlocks)

            # Learning resources from scrape
            resources = resource_map.get(t.name.lower(), [])

            nodes.append({
                "id":       str(t.topic_id),
                "type":     node_type,
                "position": {"x": round(start_x + i * NODE_W), "y": d * Y_GAP},
                "data": {
                    "label":        t.name,
                    "level":        level_str,
                    "difficulty":   _LEVEL_TO_DIFFICULTY.get(level_str, "intermediate"),
                    "description":  t.description or "",
                    "mastered":     t.mastered,
                    "prerequisites": prereq_names,
                    "unlocks":      unlock_names,
                    "depth":        d,
                    "stepIndex":    topo_idx.get(t.topic_id, 0),
                    "cluster":      cluster_map.get(t.topic_id, 0),
                    "resources":    resources,
                    "estimatedMinutes": _STUDY_TIME_MINUTES.get(level_str, 90),
                },
            })

    return nodes


def _build_edges(kg: KnowledgeGraph) -> list[dict[str, Any]]:
    """Build ReactFlow edge list from the KnowledgeGraph."""
    edges: list[dict[str, Any]] = []
    for t in kg.topics.values():
        for pid in t.prerequisites:
            edges.append({
                "id":     f"e{pid}-{t.topic_id}",
                "source": str(pid),
                "target": str(t.topic_id),
                "animated": False,
                "markerEnd": {
                    "type": "arrowclosed",
                    "width": 20,
                    "height": 20,
                    "color": "#a78bfa",
                },
            })
    return edges


def _build_learning_paths(
    kg: KnowledgeGraph,
    aco_kwargs: dict | None = None,
) -> list[dict[str, Any]]:
    """
    Build multiple learning paths with rich, actionable descriptions.

      1. Complete Path  — full topological order (every topic)
      2. Optimal Path   — ACO-optimised, smooth difficulty curve
      3. Quick Start    — foundational + intermediate only (fast wins)

    Each path carries per-step metadata so the frontend can show
    "why this order?" at every node.
    """
    paths: list[dict[str, Any]] = []
    topo = kg.learning_order()
    all_ids = [str(t.topic_id) for t in topo]

    # helper: build an ordered step list with context for a sequence of topic ids
    def _steps_with_context(topic_ids: list[int]) -> list[dict[str, str]]:
        topic_ids_set = set(topic_ids)
        steps = []
        for idx, tid in enumerate(topic_ids):
            t = kg.topics[tid]
            prereq_names = sorted(kg.topics[p].name for p in t.prerequisites)
            unlock_names = sorted(kg.topics[u].name for u in t.unlocks if u in topic_ids_set)
            level_str = t.level.name.lower() if hasattr(t.level, "name") else str(t.level)
            steps.append({
                "topicId":   str(tid),
                "name":       t.name,
                "level":      level_str,
                "requires":   prereq_names,
                "unlocks":    unlock_names,
                "reason":     (
                    "Start here — no prerequisites needed"
                    if not prereq_names
                    else f"Ready after mastering {', '.join(prereq_names)}"
                ),
            })
        return steps

    # Path 1 — full topo order
    foundations = [t for t in topo if t.level == TopicLevel.FOUNDATIONAL]
    advanced    = [t for t in topo if t.level in (TopicLevel.ADVANCED, TopicLevel.EXPERT)]
    paths.append({
        "id":          "path-full",
        "name":        "Complete Path",
        "description": (
            f"Master all {len(topo)} topics in prerequisite order — "
            f"starting with {len(foundations)} fundamentals, building to "
            f"{len(advanced)} advanced concepts."
        ),
        "duration":    f"{max(len(topo), 1)} topics",
        "difficulty":  "advanced",
        "nodeIds":     all_ids,
        "steps":       _steps_with_context([t.topic_id for t in topo]),
    })

    # Path 2 — ACO-optimised
    try:
        # Adaptive ACO sizing: small graphs → fewer ants & iterations
        K = kg.num_topics
        kw = dict(
            m=min(max(K * 2, 10), 30),
            k_max=min(max(K * 3, 15), 40),
            time_limit=4,
        )
        if aco_kwargs:
            kw.update(aco_kwargs)
        aco = LearningPathACO(kg, **kw)
        aco_path, aco_cost = aco.optimise()
        if not aco_path:
            raise ValueError("ACO returned empty path — graph may be disconnected")
        aco_ids = [str(tid) for tid in aco_path]
        paths.append({
            "id":          "path-aco",
            "name":        "Optimal Path",
            "description": (
                f"AI-optimised order that minimises difficulty jumps and keeps "
                f"related topics together (cost {aco_cost:.1f}). This path "
                f"ensures the smoothest learning curve."
            ),
            "duration":    f"{len(aco_path)} topics",
            "difficulty":  "intermediate",
            "nodeIds":     aco_ids,
            "convergence": aco.history,
            "steps":       _steps_with_context(aco_path),
        })
    except Exception as exc:
        log.warning("ACO failed: %s", exc)

    # Path 3 — quick start (foundational + intermediate only)
    quick_topics = [
        t for t in topo
        if t.level in (TopicLevel.FOUNDATIONAL, TopicLevel.INTERMEDIATE)
    ]
    if quick_topics and len(quick_topics) < len(topo):
        paths.append({
            "id":          "path-quick",
            "name":        "Quick Start",
            "description": (
                f"Cover the {len(quick_topics)} essential topics "
                f"(foundational + intermediate) to get productive fast — "
                f"skip {len(topo) - len(quick_topics)} advanced topics for later."
            ),
            "duration":    f"{len(quick_topics)} topics",
            "difficulty":  "beginner",
            "nodeIds":     [str(t.topic_id) for t in quick_topics],
            "steps":       _steps_with_context([t.topic_id for t in quick_topics]),
        })

    return paths


# ═══════════════════════════════════════════════════════════════════
# Analytics helper
# ═══════════════════════════════════════════════════════════════════
def _graph_stats(kg: KnowledgeGraph) -> dict[str, Any]:
    """Compute spectral / topological analytics + plain-English learning insights."""
    stats: dict[str, Any] = {"numTopics": kg.num_topics}
    try:
        stats["numEdges"] = int(kg.build_edge_index().size(1))
    except Exception:
        stats["numEdges"] = None
    try:
        stats["algebraicConnectivity"] = round(kg.algebraic_connectivity(), 4)
    except Exception:
        stats["algebraicConnectivity"] = None
    try:
        stats["spectralGap"] = round(kg.spectral_gap(), 4)
    except Exception:
        stats["spectralGap"] = None
    try:
        stats["connectedComponents"] = kg.betti_0()
    except Exception:
        stats["connectedComponents"] = None
    try:
        out_d = kg.out_degree()
        in_d = kg.in_degree()
        ids = sorted(kg.topics.keys())
        stats["avgOutDegree"] = round(float(out_d[ids].float().mean()), 2)
        stats["avgInDegree"]  = round(float(in_d[ids].float().mean()), 2)
        stats["maxOutDegree"] = int(out_d[ids].max())
        stats["maxInDegree"]  = int(in_d[ids].max())
    except Exception:
        pass

    # ── Learning Insights (plain-English reframing) ─────────────────
    insights: dict[str, Any] = {}

    # Curriculum Cohesion (from λ₂)
    lam2 = stats.get("algebraicConnectivity")
    if lam2 is not None:
        if lam2 >= 1.0:
            cohesion = "Strong"
            cohesion_desc = "Topics are tightly interconnected — the curriculum flows naturally."
        elif lam2 >= 0.3:
            cohesion = "Moderate"
            cohesion_desc = "The curriculum has reasonable connectivity with some independent branches."
        elif lam2 > 0.0:
            cohesion = "Weak"
            cohesion_desc = "Topics are loosely connected — consider studying related areas to bridge gaps."
        else:
            cohesion = "Disconnected"
            cohesion_desc = "Some topic groups are completely separate — you may need to study them independently."
        insights["curriculumCohesion"] = {"rating": cohesion, "description": cohesion_desc, "value": lam2}

    # Bottleneck Risk (from spectral gap + degree analysis)
    gap = stats.get("spectralGap")
    max_in = stats.get("maxInDegree", 0)
    avg_in = stats.get("avgInDegree", 0)
    if gap is not None:
        # Find chokepoint topics (high in-degree relative to average)
        chokepoints = []
        if avg_in and max_in:
            for tid, t in kg.topics.items():
                if len(t.prerequisites) >= max(max_in * 0.7, avg_in * 2, 3):
                    chokepoints.append(t.name)
        if chokepoints:
            bottleneck = "High"
            bottleneck_desc = f"{len(chokepoints)} topic(s) require many prerequisites: {', '.join(chokepoints[:3])}{'...' if len(chokepoints) > 3 else ''}. Plan extra time for these."
        elif gap < 0.1:
            bottleneck = "Moderate"
            bottleneck_desc = "The curriculum has some bottleneck points. Some topics may feel harder to reach."
        else:
            bottleneck = "Low"
            bottleneck_desc = "The learning graph is well-balanced — no major bottlenecks detected."
        insights["bottleneckRisk"] = {"rating": bottleneck, "description": bottleneck_desc, "chokepoints": chokepoints[:5]}

    # Prerequisite Load
    avg_prereqs = stats.get("avgInDegree", 0)
    max_prereqs = stats.get("maxInDegree", 0)
    if avg_prereqs is not None:
        if avg_prereqs <= 1.0:
            load_rating = "Light"
            load_desc = "Most topics have just 0-1 prerequisites — you can explore freely."
        elif avg_prereqs <= 2.0:
            load_rating = "Moderate"
            load_desc = f"Topics average {avg_prereqs} prerequisites. Follow the suggested path order for best results."
        else:
            load_rating = "Heavy"
            load_desc = f"Topics average {avg_prereqs} prerequisites (max {max_prereqs}). This curriculum is highly sequential — stick to the learning path."
        insights["prerequisiteLoad"] = {"rating": load_rating, "description": load_desc}

    # Breadth vs Depth
    components = stats.get("connectedComponents", 1)
    n_topics = stats.get("numTopics", 0)
    if n_topics > 0:
        depth_vec = kg.topological_depth_vector()
        max_depth = int(depth_vec[list(kg.topics.keys())].max()) if kg.topics else 0
        ratio = max_depth / max(n_topics, 1)
        if ratio > 0.5:
            structure = "Deep"
            structure_desc = f"This curriculum goes {max_depth} levels deep — expect to build knowledge layer by layer."
        elif ratio > 0.2:
            structure = "Balanced"
            structure_desc = f"A balanced mix of depth ({max_depth} levels) and breadth across the topic graph."
        else:
            structure = "Broad"
            structure_desc = f"This curriculum is wide with many parallel topics — great for exploring different areas."
        insights["curriculumShape"] = {"type": structure, "description": structure_desc, "depth": max_depth}

    stats["insights"] = insights
    return stats


# ═══════════════════════════════════════════════════════════════════
# Parallel learning helpers
# ═══════════════════════════════════════════════════════════════════

def _detect_bridges(spec_a: list[dict], spec_b: list[dict]) -> list[dict]:
    """
    Find conceptually similar topics across two domain specs using
    normalised string similarity (SequenceMatcher, threshold ≥ 0.65).
    """
    def _norm(s: str) -> str:
        return re.sub(r"\W+", " ", s.lower()).strip()

    bridges: list[dict] = []
    for sa in spec_a:
        for sb in spec_b:
            sim = difflib.SequenceMatcher(
                None, _norm(sa["name"]), _norm(sb["name"])
            ).ratio()
            if sim >= 0.65:
                bridges.append({
                    "nameA":       sa["name"],
                    "nameB":       sb["name"],
                    "similarity":  round(sim, 3),
                    "description": sa.get("description", "") or sb.get("description", ""),
                })
    return bridges


def _build_parallel_spec(
    skill_a: str,
    spec_a: list[dict],
    skill_b: str,
    spec_b: list[dict],
) -> tuple[list[dict], dict[str, dict]]:
    """
    Merge two topic specs for parallel learning.

    Topic names are prefixed with their source skill label
    (e.g. "Machine Learning › Linear Algebra") so the combined
    KnowledgeGraph has no name collisions.

    Returns
    -------
    merged_spec  : list of topic dicts ready for KnowledgeGraph.from_spec()
    name_to_info : prefixed_name → {domain, skill, originalName}
    """
    def _pname(skill: str, name: str) -> str:
        return f"{skill} \u203a {name}"

    merged: list[dict] = []
    name_to_info: dict[str, dict] = {}

    for s in spec_a:
        pn = _pname(skill_a, s["name"])
        merged.append({
            "name":               pn,
            "description":        s.get("description", ""),
            "level":              s.get("level", "foundational"),
            "prerequisite_names": [_pname(skill_a, p) for p in s.get("prerequisite_names", [])],
            "resources":          s.get("resources", []),
        })
        name_to_info[pn] = {"domain": "A", "skill": skill_a, "originalName": s["name"]}

    for s in spec_b:
        pn = _pname(skill_b, s["name"])
        merged.append({
            "name":               pn,
            "description":        s.get("description", ""),
            "level":              s.get("level", "foundational"),
            "prerequisite_names": [_pname(skill_b, p) for p in s.get("prerequisite_names", [])],
            "resources":          s.get("resources", []),
        })
        name_to_info[pn] = {"domain": "B", "skill": skill_b, "originalName": s["name"]}

    return merged, name_to_info


def _resolve_bridge_ids(
    kg: KnowledgeGraph,
    bridges: list[dict],
    skill_a: str,
    skill_b: str,
) -> list[tuple[int, int]]:
    """Map bridge name pairs to (topic_id_A, topic_id_B) tuples in the combined KG."""
    pairs: list[tuple[int, int]] = []
    for b in bridges:
        pname_a = f"{skill_a} \u203a {b['nameA']}"
        pname_b = f"{skill_b} \u203a {b['nameB']}"
        ta = kg.get_topic_by_name(pname_a)
        tb = kg.get_topic_by_name(pname_b)
        if ta is not None and tb is not None:
            pairs.append((ta.topic_id, tb.topic_id))
    return pairs


def _build_parallel_paths(
    kg_combined: KnowledgeGraph,
    bridge_id_pairs: list[tuple[int, int]],
    skill_a: str,
    skill_b: str,
    tid_to_info: dict[int, dict],
    diff_scores: dict[int, float],
) -> list[dict[str, Any]]:
    """
    Build learning paths for parallel study of two topics.

    Runs ParallelLearningACO on the combined graph to find an
    interleaved ordering that respects prerequisite constraints in both
    domains while grouping related cross-domain topics close together.
    Also returns per-domain solo paths for reference.
    """
    bridge_tids: set[int] = (
        {tid_a for tid_a, _ in bridge_id_pairs} |
        {tid_b for _, tid_b in bridge_id_pairs}
    )
    K = kg_combined.num_topics
    kw = dict(
        m=min(max(K * 2, 10), 40),
        k_max=min(max(K * 3, 20), 60),
        time_limit=6,
    )
    topic_domains = {
        tid: str(info.get("domain", "unknown"))
        for tid, info in tid_to_info.items()
    }
    aco = ParallelLearningACO(
        kg_combined,
        bridge_id_pairs=bridge_id_pairs,
        topic_domains=topic_domains,
        **kw,
    )
    aco_path, aco_cost = aco.optimise()

    def _step(tid: int) -> dict[str, Any]:
        t = kg_combined.topics[tid]
        info = tid_to_info.get(tid, {})
        level_str = t.level.name.lower() if hasattr(t.level, "name") else str(t.level)
        prereq_names = sorted(
            (tid_to_info.get(p, {}).get("originalName") or kg_combined.topics[p].name)
            for p in t.prerequisites
        )
        synergy: str | None = None
        if tid in bridge_tids:
            other = skill_b if info.get("domain") == "A" else skill_a
            synergy = (
                f"This concept also appears in {other} — mastering it here "
                "gives you a head start in both domains."
            )
        return {
            "topicId":      str(tid),
            "name":         info.get("originalName", t.name),
            "displayName":  t.name,
            "domain":       info.get("domain", "unknown"),
            "skill":        info.get("skill", ""),
            "level":        level_str,
            "difficulty":   round(diff_scores.get(tid, 0.5), 3),
            "isBridge":     tid in bridge_tids,
            "requires":     prereq_names,
            "synergy":      synergy,
            "reason": (
                "Start here — no prerequisites needed"
                if not prereq_names
                else f"Ready after: {', '.join(prereq_names[:2])}"
            ),
        }

    steps = [_step(tid) for tid in aco_path]
    domain_a = sum(1 for s in steps if s["domain"] == "A")
    domain_b = sum(1 for s in steps if s["domain"] == "B")
    # Count bridge PAIRS where both topics appear in the path (not individual topics)
    path_set = set(aco_path)
    bridges_hit = sum(
        1 for tid_a, tid_b in bridge_id_pairs
        if tid_a in path_set and tid_b in path_set
    )

    paths: list[dict[str, Any]] = [{
        "id":          "path-parallel-aco",
        "name":        "Parallel Learning Path",
        "description": (
            f"AI-optimised interleaved path covering both {skill_a} ({domain_a} topics) "
            f"and {skill_b} ({domain_b} topics). "
            f"{bridges_hit} bridge concept(s) connect the two domains."
        ),
        "duration":    f"{len(aco_path)} topics",
        "difficulty":  "intermediate",
        "type":        "parallel",
        "skills":      [skill_a, skill_b],
        "nodeIds":     [str(tid) for tid in aco_path],
        "steps":       steps,
        "convergence": aco.history,
        "cost":        round(aco_cost, 2),
        "bridges":     bridges_hit,
    }]

    # Per-domain solo paths for reference
    topo = kg_combined.learning_order()
    for skill, domain_tag in [(skill_a, "A"), (skill_b, "B")]:
        domain_topics = [
            t for t in topo
            if tid_to_info.get(t.topic_id, {}).get("domain") == domain_tag
        ]
        paths.append({
            "id":          f"path-{domain_tag.lower()}-solo",
            "name":        f"{skill} Only",
            "description": f"Study {skill} independently ({len(domain_topics)} topics).",
            "duration":    f"{len(domain_topics)} topics",
            "difficulty":  "intermediate",
            "type":        "single",
            "skills":      [skill],
            "nodeIds":     [str(t.topic_id) for t in domain_topics],
            "steps":       [_step(t.topic_id) for t in domain_topics],
        })

    return paths


def _parallel_benefits(
    bridges: list[dict],
    kg_a: KnowledgeGraph,
    kg_b: KnowledgeGraph,
    skill_a: str,
    skill_b: str,
) -> dict[str, Any]:
    """Analyse the synergy and time-saving benefits of parallel learning."""
    total_a = kg_a.num_topics
    total_b = kg_b.num_topics
    shared = len(bridges)

    synergy_score = min(shared / max(min(total_a, total_b), 1), 1.0)
    if synergy_score >= 0.5:
        label, desc = "High", (
            f"{skill_a} and {skill_b} share significant common ground — "
            "parallel learning is strongly recommended."
        )
    elif synergy_score >= 0.25:
        label, desc = "Moderate", (
            "These topics share enough concepts to benefit meaningfully from parallel study."
        )
    else:
        label, desc = "Low", (
            "These topics are largely independent — parallel study still works "
            "but offers fewer direct synergies."
        )

    return {
        "synergy": {
            "score":       round(synergy_score, 3),
            "label":       label,
            "description": desc,
        },
        "sharedConcepts": {
            "count": shared,
            "items": [
                {"skillA": b["nameA"], "skillB": b["nameB"], "similarity": b["similarity"]}
                for b in bridges[:8]
            ],
            "insight": (
                f"{shared} concept(s) appear in both curricula — "
                "mastering them once benefits both topics."
                if shared
                else "No direct shared concepts detected — the two topics complement each other."
            ),
        },
        "estimatedSaving": {
            "totalTopicsSequential": total_a + total_b,
            "sharedConceptReuse":    shared,
            "description": (
                f"Sequential learning: {total_a} + {total_b} = {total_a + total_b} topics. "
                f"Parallel learning with {shared} shared concept(s) reduces redundant effort."
            ),
        },
        "recommendedApproach": (
            f"Study {skill_a} and {skill_b} side-by-side. "
            "When you reach a bridge topic, deepen your understanding in both contexts simultaneously. "
            "The parallel ACO path already sequences bridge topics at optimal interleaving points."
        ),
    }


# ═══════════════════════════════════════════════════════════════════
# Routes
# ═══════════════════════════════════════════════════════════════════
@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "dictionary_size": len(_dict)})


@app.route("/api/generate", methods=["POST"])
def generate_graph():
    """
    Build a full knowledge graph for a skill.

    Request JSON:  { "skill": "Machine Learning" }
    Response JSON: { "nodes": [...], "edges": [...], "paths": [...], "skill": "..." }
    """
    body = request.get_json(silent=True) or {}
    skill = (body.get("skill") or "").strip()
    if not skill:
        return jsonify({"error": "missing 'skill' field"}), 400

    log.info("generate  skill=%r", skill)
    t0 = time.time()

    try:
        # 1. Webscrape subtopics
        spec = get_learning_spec(skill)
        t_scrape = time.time() - t0
        if not spec:
            return jsonify({"error": f"no subtopics found for '{skill}'"}), 404

        # 2. Build knowledge graph (should be < 1 ms)
        t1 = time.time()
        kg = KnowledgeGraph.from_spec(spec)
        t_graph = time.time() - t1

        # Store graph for mastery / shortest-path queries
        _store_graph(skill.lower(), (kg, spec))

        # 3. Layout + edges + paths + stats (should be < 50 ms total)
        t2 = time.time()
        nodes = _layout_nodes(kg, spec)
        t_layout = time.time() - t2

        t3 = time.time()
        edges = _build_edges(kg)
        t_edges = time.time() - t3

        t4 = time.time()
        paths = _build_learning_paths(kg)
        t_paths = time.time() - t4

        t5 = time.time()
        stats = _graph_stats(kg)
        t_stats = time.time() - t5

        elapsed = time.time() - t0
        compute_ms = (t_graph + t_layout + t_edges + t_paths + t_stats) * 1000
        log.info(
            "generate  skill=%r  topics=%d  elapsed=%.2fs  "
            "(scrape=%.2fs  graph=%.1fms  layout=%.1fms  edges=%.1fms  paths=%.1fms  stats=%.1fms)",
            skill, kg.num_topics, elapsed,
            t_scrape, t_graph * 1000, t_layout * 1000, t_edges * 1000, t_paths * 1000, t_stats * 1000,
        )

        return jsonify({
            "skill":   skill,
            "nodes":   nodes,
            "edges":   edges,
            "paths":   paths,
            "stats":   stats,
            "elapsed": round(elapsed, 2),
            "timing": {
                "scrape_s":    round(t_scrape, 3),
                "graph_ms":    round(t_graph * 1000, 2),
                "layout_ms":   round(t_layout * 1000, 2),
                "edges_ms":    round(t_edges * 1000, 2),
                "paths_ms":    round(t_paths * 1000, 2),
                "stats_ms":    round(t_stats * 1000, 2),
                "compute_ms":  round(compute_ms, 2),
            },
        })

    except Exception as exc:
        log.error("generate failed: %s\n%s", exc, traceback.format_exc())
        return jsonify({"error": str(exc)}), 500


@app.route("/api/sub-graph", methods=["POST"])
def sub_graph():
    """
    Generate a sub-graph for a specific subtopic.

    Request JSON:  { "topic": "Neural Networks" }
    Response JSON: { "nodes": [...], "edges": [...], "paths": [...], "skill": "..." }
    """
    body = request.get_json(silent=True) or {}
    topic = (body.get("topic") or "").strip()
    if not topic:
        return jsonify({"error": "missing 'topic' field"}), 400

    log.info("sub-graph  topic=%r", topic)
    t0 = time.time()

    try:
        spec = get_learning_spec(topic)
        t_scrape = time.time() - t0
        if not spec:
            return jsonify({"error": f"no subtopics found for '{topic}'"}), 404

        t1 = time.time()
        kg = KnowledgeGraph.from_spec(spec)
        t_graph = time.time() - t1

        t2 = time.time()
        nodes = _layout_nodes(kg, spec)
        t_layout = time.time() - t2

        edges = _build_edges(kg)
        paths = _build_learning_paths(kg)
        stats = _graph_stats(kg)
        compute_ms = (time.time() - t1) * 1000

        # Store sub-graph so mastery/shortest-path work for it too
        _store_graph(topic.lower(), (kg, spec))

        log.info(
            "sub-graph  topic=%r  topics=%d  compute=%.1fms  scrape=%.2fs",
            topic, kg.num_topics, compute_ms, t_scrape,
        )

        return jsonify({
            "skill": topic,
            "nodes": nodes,
            "edges": edges,
            "paths": paths,
            "stats": stats,
            "timing": {
                "scrape_s":   round(t_scrape, 3),
                "compute_ms": round(compute_ms, 2),
            },
        })

    except Exception as exc:
        log.error("sub-graph failed: %s", exc)
        return jsonify({"error": str(exc)}), 500


@app.route("/api/spell-check", methods=["POST"])
def spell_check():
    """
    Spell-correct a word or phrase using SDS.

    Request JSON:  { "text": "mathmatics" }
                or { "text": "mathmatics", "top_k": 5 }
    Response JSON: { "results": [ { "original": "...", "suggestions": [...] } ] }
    """
    body = request.get_json(silent=True) or {}
    text = (body.get("text") or "").strip()
    top_k = body.get("top_k", 5)
    if not text:
        return jsonify({"error": "missing 'text' field"}), 400

    log.info("spell-check  text=%r", text)

    try:
        per_word = correct_phrase(text, top_k=top_k)
        tokens = text.split()
        results = []

        for token, suggestions in zip(tokens, per_word):
            results.append({
                "original":    token,
                "suggestions": [
                    {"word": w, "score": round(sc, 4)}
                    for w, sc in suggestions
                ],
                "inDictionary": len(suggestions) == 1 and suggestions[0][1] == 1.0,
            })

        return jsonify({"results": results})

    except Exception as exc:
        log.error("spell-check failed: %s", exc)
        return jsonify({"error": str(exc)}), 500


@app.route("/api/master", methods=["POST"])
def master_topic():
    """
    Mark a topic as mastered (prerequisite-validated).

    Request JSON:  { "skill": "Machine Learning", "topicId": "3" }
    Response JSON: { "success": true, "mastered": [...], "available": [...],
                     "locked": [...], "progress": 0.42 }
    """
    body = request.get_json(silent=True) or {}
    skill = (body.get("skill") or "").strip().lower()
    topic_id_str = body.get("topicId", "")

    if not skill or topic_id_str == "":
        return jsonify({"error": "missing 'skill' and/or 'topicId'"}), 400

    entry = _get_graph(skill)
    if not entry:
        return jsonify({"error": f"no graph stored for '{skill}' — generate first"}), 404

    kg, _ = entry
    try:
        tid = int(topic_id_str)
    except (ValueError, TypeError):
        return jsonify({"error": f"invalid topicId: {topic_id_str}"}), 400

    if tid not in kg.topics:
        return jsonify({"error": f"topic {tid} not found in graph"}), 404

    with _get_kg_lock(skill):
        success = kg.master_topic(tid)
        # Capture all KG state while still under the lock to prevent race conditions
        mastered_list = [{"id": str(t.topic_id), "name": t.name} for t in kg.get_mastered()]
        available_list = [{"id": str(t.topic_id), "name": t.name} for t in kg.get_available()]
        locked_list = [{"id": str(t.topic_id), "name": t.name} for t in kg.get_locked()]
        progress_val = round(kg.mastery_progress(), 4)
        
        if not success:
            missing = [
                kg.topics[p].name for p in kg.topics[tid].prerequisites
                if not kg.topics[p].mastered
            ]
            # Return 200 with success=false so the frontend can read the body
            return jsonify({
                "success": False,
                "reason": f"prerequisites not met: {', '.join(missing)}",
                "mastered":  mastered_list,
                "available": available_list,
                "locked":    locked_list,
                "progress":  progress_val,
            })

        return jsonify({
            "success":   True,
            "mastered":  mastered_list,
            "available": available_list,
            "locked":    locked_list,
            "progress":  progress_val,
        })


@app.route("/api/shortest-path", methods=["POST"])
def shortest_path():
    """
    Find the minimum topics needed to reach a target topic.

    Request JSON:  { "skill": "Machine Learning", "targetId": "7" }
    Response JSON: { "path": [ {"id": "0", "name": "...", "mastered": false}, ... ] }
    """
    body = request.get_json(silent=True) or {}
    skill = (body.get("skill") or "").strip().lower()
    target_str = body.get("targetId", "")

    if not skill or target_str == "":
        return jsonify({"error": "missing 'skill' and/or 'targetId'"}), 400

    entry = _get_graph(skill)
    if not entry:
        return jsonify({"error": f"no graph stored for '{skill}' — generate first"}), 404

    kg, _ = entry
    try:
        target_id = int(target_str)
    except (ValueError, TypeError):
        return jsonify({"error": f"invalid targetId: {target_str}"}), 400

    if target_id not in kg.topics:
        return jsonify({"error": f"topic {target_id} not found"}), 404

    sp = kg.shortest_path_to(target_id)
    return jsonify({
        "path": [
            {
                "id":       str(t.topic_id),
                "name":     t.name,
                "mastered": t.mastered,
                "level":    t.level.name.lower(),
            }
            for t in sp
        ],
    })


@app.route("/api/progress/<skill>", methods=["GET"])
def get_progress(skill: str):
    """
    Return mastery state for a previously generated graph.

    Response JSON: { "mastered": [...], "available": [...],
                     "locked": [...], "progress": 0.42 }
    """
    entry = _get_graph(skill.lower())
    if not entry:
        return jsonify({"error": f"no graph stored for '{skill}'"}), 404

    kg, _ = entry
    return jsonify({
        "mastered":  [{"id": str(t.topic_id), "name": t.name} for t in kg.get_mastered()],
        "available": [{"id": str(t.topic_id), "name": t.name} for t in kg.get_available()],
        "locked":    [{"id": str(t.topic_id), "name": t.name} for t in kg.get_locked()],
        "progress":  round(kg.mastery_progress(), 4),
    })


@app.route("/api/spectral-positions/<skill>", methods=["GET"])
def get_spectral_positions(skill: str):
    """
    Return 2D spectral embedding positions for all topics.
    
    Uses topological spectral graph theory (Fiedler vector) for layout.
    Frontend can use these for force-directed or spectral rendering.
    
    Response JSON: { "positions": {topicId: [x, y], ...}, "metadata": {...} }
    """
    entry = _get_graph(skill.lower())
    if not entry:
        return jsonify({"error": f"no graph stored for '{skill}'"}), 404
    
    kg, _ = entry
    try:
        positions = kg.spectral_graph_positions()
        positions_normalized = {}
        for tid, (x, y) in positions.items():
            positions_normalized[str(tid)] = [round(float(x), 4), round(float(y), 4)]

        try:
            eigenvalues = [round(float(v), 4) for v in kg.spectral_eigenvalues(k=3)]
        except Exception:
            eigenvalues = []
        try:
            alg_conn = round(kg.algebraic_connectivity(), 4)
        except Exception:
            alg_conn = None

        return jsonify({
            "positions": positions_normalized,
            "metadata": {
                "method": "spectral_laplacian",
                "eigenvalues": eigenvalues,
                "algebraicConnectivity": alg_conn,
            }
        })
    except Exception as exc:
        log.error("spectral-positions failed: %s", exc)
        return jsonify({"error": str(exc)}), 500


@app.route("/api/difficulty/<skill>", methods=["GET"])
def get_difficulty(skill: str):
    """
    Predict per-topic difficulty using the GAT model.
    
    Response JSON: { "difficulties": {topicId: score, ...}, "recommendations": [...] }
    """
    _ensure_difficulty_gnn()
    entry = _get_graph(skill.lower())
    if not entry:
        return jsonify({"error": f"no graph stored for '{skill}'"}), 404
    
    kg, _ = entry
    mastered_ids = {t.topic_id for t in kg.get_mastered()}
    
    try:
        scores = _predict_difficulty(kg, mastered_ids, skill_key=skill.lower())
        recommendations = _get_smart_recommendation(kg, mastered_ids, skill_key=skill.lower(), precomputed_scores=scores)
        
        diffs = {str(tid): round(score, 4) for tid, score in scores.items()}
        recs = [
            {
                "id": str(r["topicId"]),
                "name": r["name"],
                "difficulty": round(r.get("difficulty", 0.5), 4),
                "reason": r.get("reason", ""),
            }
            for r in recommendations[:10]
        ]
        
        return jsonify({"difficulties": diffs, "recommendations": recs})
    except Exception as exc:
        log.error("difficulty endpoint failed: %s", exc)
        return jsonify({"error": str(exc)}), 500


@app.route("/api/learning-paths/<skill>", methods=["GET"])
def get_learning_paths(skill: str):
    """
    Return all learning paths (Full, Optimal, Quick Start) with detailed steps.
    
    Response JSON: { "paths": [{id, name, steps, ...}, ...] }
    """
    entry = _get_graph(skill.lower())
    if not entry:
        return jsonify({"error": f"no graph stored for '{skill}'"}), 404
    
    kg, spec = entry
    paths = _build_learning_paths(kg)
    
    return jsonify({"paths": paths, "totalTopics": kg.num_topics})


@app.route("/api/aco-path", methods=["POST"])
def get_aco_path_for_topics():
    """
    Compute an ACO-optimized learning path from ad-hoc NeuroMap topics/relations.

    Request JSON:
    {
      "topics": [{"id","name","description","difficulty", ...}],
      "relations": [{"source","target","type", ...}]
    }

    Response JSON:
    {
      "path": [{"topicId","name","order","reason","requires":[]}],
      "cost": number,
      "convergence": [...]
    }
    """
    body = request.get_json(silent=True) or {}
    topics = body.get("topics") or []
    relations = body.get("relations") or []

    if not isinstance(topics, list) or len(topics) == 0:
        return jsonify({"error": "topics must be a non-empty array"}), 400
    if not isinstance(relations, list):
        return jsonify({"error": "relations must be an array"}), 400

    id_to_topic: dict[str, dict[str, Any]] = {}
    for t in topics:
        if not isinstance(t, dict):
            continue
        tid = str(t.get("id", "")).strip()
        name = str(t.get("name", "")).strip()
        if tid and name:
            id_to_topic[tid] = t

    if not id_to_topic:
        return jsonify({"error": "no valid topics provided"}), 400

    level_map = {
        "beginner": "foundational",
        "intermediate": "intermediate",
        "advanced": "advanced",
        "expert": "advanced",
    }

    prereq_ids_by_target: dict[str, set[str]] = {tid: set() for tid in id_to_topic}
    for r in relations:
        if not isinstance(r, dict):
            continue
        rtype = str(r.get("type", "")).lower()
        if rtype not in {"prerequisite", "hierarchical"}:
            continue
        source = str(r.get("source", "")).strip()
        target = str(r.get("target", "")).strip()
        if source in id_to_topic and target in id_to_topic and source != target:
            prereq_ids_by_target[target].add(source)

    spec: list[dict[str, Any]] = []
    for tid, t in id_to_topic.items():
        name = str(t.get("name", "")).strip()
        diff = str(t.get("difficulty", "intermediate")).lower()
        level = level_map.get(diff, "intermediate")
        prereq_names = [
            str(id_to_topic[pid].get("name", "")).strip()
            for pid in sorted(prereq_ids_by_target.get(tid, set()))
            if pid in id_to_topic
        ]
        spec.append({
            "name": name,
            "description": str(t.get("description", "") or ""),
            "level": level,
            "prerequisite_names": prereq_names,
            "resources": t.get("resources", []) if isinstance(t.get("resources", []), list) else [],
        })

    try:
        kg = KnowledgeGraph.from_spec(spec)
        K = max(kg.num_topics, 1)
        aco = LearningPathACO(
            kg,
            m=min(max(K * 2, 10), 40),
            k_max=min(max(K * 3, 20), 60),
            time_limit=6,
        )
        path_ids, cost = aco.optimise()

        steps: list[dict[str, Any]] = []
        for idx, tid in enumerate(path_ids, start=1):
            topic = kg.topics.get(tid)
            if topic is None:
                continue
            prereq_names = sorted(kg.topics[p].name for p in topic.prerequisites if p in kg.topics)
            steps.append({
                "topicId": str(tid),
                "name": topic.name,
                "order": idx,
                "requires": prereq_names,
                "reason": (
                    "Start here — no prerequisites needed"
                    if not prereq_names
                    else f"Builds on: {', '.join(prereq_names[:2])}"
                ),
            })

        return jsonify({
            "path": steps,
            "cost": round(float(cost), 3),
            "convergence": [round(float(v), 4) for v in aco.history],
            "totalTopics": kg.num_topics,
            "method": "aco",
        })
    except Exception as exc:
        log.error("aco-path failed: %s\n%s", exc, traceback.format_exc())
        return jsonify({"error": str(exc)}), 500


@app.route("/api/overall-difficulty", methods=["POST"])
def get_overall_difficulty_for_topics():
    """
    Predict per-topic difficulty for ad-hoc NeuroMap topics/relations.

    Request JSON:
    {
      "topics": [{"id","name","description","difficulty", ...}],
      "relations": [{"source","target","type", ...}]
    }

    Response JSON:
    {
      "difficulties": {"topicId": score, ...},
      "recommendations": [{"id","name","difficulty","reason"}, ...]
    }
    """
    _ensure_difficulty_gnn()

    body = request.get_json(silent=True) or {}
    topics = body.get("topics") or []
    relations = body.get("relations") or []

    if not isinstance(topics, list) or len(topics) == 0:
        return jsonify({"error": "topics must be a non-empty array"}), 400
    if not isinstance(relations, list):
        return jsonify({"error": "relations must be an array"}), 400

    id_to_topic: dict[str, dict[str, Any]] = {}
    for t in topics:
        if not isinstance(t, dict):
            continue
        tid = str(t.get("id", "")).strip()
        name = str(t.get("name", "")).strip()
        if tid and name:
            id_to_topic[tid] = t

    if not id_to_topic:
        return jsonify({"error": "no valid topics provided"}), 400

    level_map = {
        "beginner": "foundational",
        "intermediate": "intermediate",
        "advanced": "advanced",
        "expert": "advanced",
    }

    # Use id-scoped internal names so duplicate labels do not collide.
    internal_name_by_id = {
        tid: f"{str(t.get('name', '')).strip()} [id:{tid}]"
        for tid, t in id_to_topic.items()
    }

    prereq_ids_by_target: dict[str, set[str]] = {tid: set() for tid in id_to_topic}
    for r in relations:
        if not isinstance(r, dict):
            continue
        rtype = str(r.get("type", "")).lower()
        if rtype not in {"prerequisite", "hierarchical"}:
            continue
        source = str(r.get("source", "")).strip()
        target = str(r.get("target", "")).strip()
        if source in id_to_topic and target in id_to_topic and source != target:
            prereq_ids_by_target[target].add(source)

    spec: list[dict[str, Any]] = []
    for tid, t in id_to_topic.items():
        diff = str(t.get("difficulty", "intermediate")).lower()
        level = level_map.get(diff, "intermediate")
        prereq_names = [
            internal_name_by_id[pid]
            for pid in sorted(prereq_ids_by_target.get(tid, set()))
            if pid in internal_name_by_id
        ]
        spec.append({
            "name": internal_name_by_id[tid],
            "description": str(t.get("description", "") or ""),
            "level": level,
            "prerequisite_names": prereq_names,
            "resources": t.get("resources", []) if isinstance(t.get("resources", []), list) else [],
        })

    try:
        kg = KnowledgeGraph.from_spec(spec)
        scores = _predict_difficulty(kg, set(), skill_key="overall-neuromap")

        # Map scores back to original topic ids
        diff_by_topic_id: dict[str, float] = {}
        kg_id_to_topic_id: dict[int, str] = {}
        for topic_id, internal_name in internal_name_by_id.items():
            t = kg.get_topic_by_name(internal_name)
            if t is None:
                continue
            kg_id_to_topic_id[t.topic_id] = topic_id
            diff_by_topic_id[topic_id] = round(float(scores.get(t.topic_id, 0.5)), 4)

        recommendations_raw = _get_smart_recommendation(
            kg,
            set(),
            skill_key="overall-neuromap",
            precomputed_scores=scores,
        )

        recommendations: list[dict[str, Any]] = []
        for r in recommendations_raw[:10]:
            topic_id_raw = r.get("topicId", -1)
            kg_tid = int(topic_id_raw) if str(topic_id_raw).isdigit() else -1
            if kg_tid < 0:
                continue
            original_tid = kg_id_to_topic_id.get(kg_tid)
            if not original_tid:
                continue
            topic_name = str(id_to_topic.get(original_tid, {}).get("name", r.get("name", "")))
            recommendations.append({
                "id": original_tid,
                "name": topic_name,
                "difficulty": round(float(r.get("difficulty", diff_by_topic_id.get(original_tid, 0.5))), 4),
                "reason": str(r.get("reason", "")),
            })

        return jsonify({
            "difficulties": diff_by_topic_id,
            "recommendations": recommendations,
        })

    except Exception as exc:
        log.error("overall-difficulty failed: %s\n%s", exc, traceback.format_exc())
        return jsonify({"error": str(exc)}), 500



@app.route("/api/summary/<skill>/<topic_id>", methods=["GET"])
def get_topic_summary(skill: str, topic_id: str):
    """
    Return an AI-style summary for a single topic node.

    Combines the scraped description, GNN difficulty analysis, and graph
    structure into a structured, human-readable summary.

    Response JSON: {
        topicId, name, level, difficultyScore, difficultyExplanation,
        description, keyPoints, studyTip, resources, depth,
        prerequisiteCount, unlocksCount, estimatedMinutes
    }
    """
    entry = _get_graph(skill.lower())
    if not entry:
        return jsonify({"error": f"no graph stored for '{skill}' — generate first"}), 404

    kg, spec = entry
    try:
        tid = int(topic_id)
    except (ValueError, TypeError):
        return jsonify({"error": f"invalid topicId: {topic_id}"}), 400

    if tid not in kg.topics:
        return jsonify({"error": f"topic {tid} not found in graph"}), 404

    t = kg.topics[tid]
    level_str = t.level.name.lower() if hasattr(t.level, "name") else str(t.level)

    # Topological depth
    try:
        depth_vec = kg.topological_depth_vector()
        depth = int(depth_vec[tid])
    except (IndexError, KeyError, TypeError):
        depth = 0

    # GAT difficulty score + explanation
    _ensure_difficulty_gnn()
    mastered_ids = {t2.topic_id for t2 in kg.get_mastered()}
    try:
        scores = _predict_difficulty(kg, mastered_ids, skill_key=skill.lower())
        score = scores.get(tid, 0.5)
        explanation = _get_difficulty_explanation(kg, tid, score)
    except Exception:
        score = 0.5
        explanation = "Difficulty analysis unavailable."

    # Description + resources from spec
    spec_entry = next(
        (s for s in spec if s.get("name", "").lower() == t.name.lower()), {}
    )
    description = spec_entry.get("description", "") or t.description or ""
    resources = spec_entry.get("resources", [])[:5]

    # Key points from graph structure
    prereq_names = [kg.topics[p].name for p in t.prerequisites if p in kg.topics]
    unlock_names = [kg.topics[u].name for u in t.unlocks if u in kg.topics]

    key_points: list[str] = []
    if prereq_names:
        shown = prereq_names[:3]
        key_points.append(
            f"Requires: {', '.join(shown)}"
            + (" …" if len(prereq_names) > 3 else "")
        )
    else:
        key_points.append("No prerequisites — you can start this immediately.")
    if unlock_names:
        shown_u = unlock_names[:3]
        key_points.append(
            f"Unlocks: {', '.join(shown_u)}"
            + (" …" if len(unlock_names) > 3 else "")
        )
    if depth == 0:
        key_points.append("Root concept — a natural starting point in the curriculum.")
    elif depth >= 3:
        key_points.append(
            f"Depth {depth} in the graph — builds on substantial prior knowledge."
        )

    study_tips = {
        "foundational": (
            "Review basic definitions first, then work through simple examples "
            "before moving on to harder material."
        ),
        "intermediate": (
            "Actively connect this topic to things you already know. "
            "Practice exercises are more effective than re-reading."
        ),
        "advanced": (
            "Work through worked examples methodically and cross-reference "
            "with your prerequisites frequently."
        ),
        "expert": (
            "Engage with primary sources and papers. Apply knowledge to "
            "real problems — teaching others also deepens understanding."
        ),
    }

    return jsonify({
        "topicId":               topic_id,
        "name":                  t.name,
        "level":                 level_str,
        "difficultyScore":       round(score, 3),
        "difficultyExplanation": explanation,
        "description":           description,
        "keyPoints":             key_points,
        "studyTip":              study_tips.get(level_str, study_tips["intermediate"]),
        "resources":             resources,
        "depth":                 depth,
        "prerequisiteCount":     len(t.prerequisites),
        "unlocksCount":          len(t.unlocks),
        "estimatedMinutes":      _STUDY_TIME_MINUTES.get(level_str, 90),
    })


@app.route("/api/generate-parallel", methods=["POST"])
def generate_parallel():
    """
    Build parallel learning paths for two topics.

    Request JSON:
        { "skills": ["Machine Learning", "Statistics"] }

    Response JSON:
        {
          "skills": [...],
          "nodes": [...],          // combined graph nodes (domain-annotated)
          "edges": [...],
          "paths": [...],          // parallel ACO path + per-domain solo paths
          "bridges": [...],        // shared concepts across topics
          "benefits": {...},       // synergy analysis
          "stats": {...},          // per-topic + combined spectral stats
          "difficultyScores": {...} // GAT difficulty meter per topic
        }
    """
    body = request.get_json(silent=True) or {}
    raw_skills = body.get("skills") or []
    skills = [s.strip() for s in raw_skills if isinstance(s, str) and s.strip()]
    # De-duplicate while preserving order (case-insensitive)
    seen: set[str] = set()
    unique_skills: list[str] = []
    for s in skills:
        k = s.lower()
        if k not in seen:
            seen.add(k)
            unique_skills.append(s)
    skills = unique_skills

    if len(skills) < 2:
        return jsonify({"error": "provide at least 2 distinct skills in the 'skills' array"}), 400

    log.info("generate-parallel  skills=%r", skills)
    t0 = time.time()

    try:
        # 1. Scrape all topics concurrently
        with ThreadPoolExecutor(max_workers=min(len(skills), 6)) as ex:
            futures = {skill: ex.submit(get_learning_spec, skill) for skill in skills}
            specs: dict[str, list[dict]] = {skill: fut.result() for skill, fut in futures.items()}
        t_scrape = time.time() - t0

        for skill in skills:
            if not specs.get(skill):
                return jsonify({"error": f"no subtopics found for '{skill}'"}), 404

        # 2. Individual KGs (for per-topic stats + benefits)
        per_skill_kg: dict[str, KnowledgeGraph] = {
            skill: KnowledgeGraph.from_spec(specs[skill])
            for skill in skills
        }

        # 3. Detect bridge concepts pairwise across all skills
        bridges: list[dict[str, Any]] = []
        for skill_a, skill_b in combinations(skills, 2):
            pair_bridges = _detect_bridges(specs[skill_a], specs[skill_b])
            for b in pair_bridges:
                bridges.append({
                    "skillA": skill_a,
                    "skillB": skill_b,
                    "nameA": b["nameA"],
                    "nameB": b["nameB"],
                    "similarity": b["similarity"],
                    "description": b.get("description", ""),
                })

        # 4. Build combined spec with skill-prefixed names
        merged_spec: list[dict[str, Any]] = []
        name_to_info: dict[str, dict[str, Any]] = {}
        for idx, skill_name in enumerate(skills):
            domain = chr(ord("A") + idx) if idx < 26 else f"S{idx + 1}"
            for s in specs[skill_name]:
                pref_name = f"{skill_name} › {s['name']}"
                merged_spec.append({
                    "name": pref_name,
                    "description": s.get("description", ""),
                    "level": s.get("level", "foundational"),
                    "prerequisite_names": [f"{skill_name} › {p}" for p in s.get("prerequisite_names", [])],
                    "resources": s.get("resources", []),
                })
                name_to_info[pref_name] = {
                    "domain": domain,
                    "skill": skill_name,
                    "originalName": s["name"],
                }

        # 5. Build combined KG
        t1 = time.time()
        kg_combined = KnowledgeGraph.from_spec(merged_spec)
        # Map topic_id -> domain info
        tid_to_info: dict[int, dict[str, Any]] = {}
        for s in merged_spec:
            t = kg_combined.get_topic_by_name(s["name"])
            if t is not None:
                tid_to_info[t.topic_id] = name_to_info.get(s["name"], {})
        t_graph = time.time() - t1

        # Store graphs for mastery / shortest-path endpoints
        for skill_name in skills:
            _store_graph(skill_name.lower(), (per_skill_kg[skill_name], specs[skill_name]))
        # URL-encode each skill then join with a delimiter that cannot appear
        # in encoded segments to avoid key collisions (e.g., skills containing '+').
        combined_key = "|||".join(quote(s.lower(), safe="") for s in skills)
        _store_graph(combined_key, (kg_combined, merged_spec))

        # 6. Resolve bridge topic IDs in the combined KG
        bridge_id_pairs: list[tuple[int, int]] = []
        for b in bridges:
            pname_a = f"{b['skillA']} › {b['nameA']}"
            pname_b = f"{b['skillB']} › {b['nameB']}"
            ta = kg_combined.get_topic_by_name(pname_a)
            tb = kg_combined.get_topic_by_name(pname_b)
            if ta is not None and tb is not None:
                bridge_id_pairs.append((ta.topic_id, tb.topic_id))

        bridge_tids = (
            {tid_a for tid_a, _ in bridge_id_pairs} |
            {tid_b for _, tid_b in bridge_id_pairs}
        )

        # 7. Layout — reuse existing helper, then annotate with domain info
        t2 = time.time()
        nodes = _layout_nodes(kg_combined, merged_spec)
        for node in nodes:
            tid = int(node["id"])
            info = tid_to_info.get(tid, {})
            node["data"]["sourceDomain"]  = info.get("domain", "unknown")
            node["data"]["sourceSkill"]   = info.get("skill", "")
            node["data"]["originalName"]  = info.get("originalName", node["data"]["label"])
            node["data"]["isBridge"]      = tid in bridge_tids
        edges = _build_edges(kg_combined)
        t_layout = time.time() - t2

        # 8. Difficulty prediction on combined graph (GAT meter or heuristic fallback)
        t3 = time.time()
        _ensure_difficulty_gnn()
        diff_scores = _predict_difficulty(kg_combined, skill_key=combined_key)
        for node in nodes:
            tid = int(node["id"])
            node["data"]["difficultyScore"] = round(diff_scores.get(tid, 0.5), 3)
        t_diff = time.time() - t3

        # 9. Learning paths: specialised 2-skill interleaved path, or multi-skill ACO
        t4 = time.time()
        if len(skills) == 2:
            paths = _build_parallel_paths(
                kg_combined,
                bridge_id_pairs,
                skills[0],
                skills[1],
                tid_to_info,
                diff_scores,
            )
        else:
            K = kg_combined.num_topics
            aco = LearningPathACO(
                kg_combined,
                m=min(max(K * 2, 10), 40),
                k_max=min(max(K * 3, 20), 60),
                time_limit=8,
            )
            aco_path, aco_cost = aco.optimise()

            def _step(tid: int) -> dict[str, Any]:
                t = kg_combined.topics[tid]
                info = tid_to_info.get(tid, {})
                level_str = t.level.name.lower() if hasattr(t.level, "name") else str(t.level)
                prereq_names = sorted(
                    (tid_to_info.get(p, {}).get("originalName") or kg_combined.topics[p].name)
                    for p in t.prerequisites
                )
                return {
                    "topicId": str(tid),
                    "name": info.get("originalName", t.name),
                    "displayName": t.name,
                    "domain": info.get("domain", "unknown"),
                    "skill": info.get("skill", ""),
                    "level": level_str,
                    "difficulty": round(diff_scores.get(tid, 0.5), 3),
                    "isBridge": tid in bridge_tids,
                    "requires": prereq_names,
                    "reason": (
                        "Start here — no prerequisites needed"
                        if not prereq_names
                        else f"Ready after: {', '.join(prereq_names[:2])}"
                    ),
                }

            steps = [_step(tid) for tid in aco_path]
            paths = [{
                "id": "path-multiskill-aco",
                "name": "Multi-Skill Learning Path",
                "description": (
                    f"AI-optimised interleaved path across {len(skills)} skills "
                    f"with {len(bridge_id_pairs)} bridge concept pair(s)."
                ),
                "duration": f"{len(aco_path)} topics",
                "difficulty": "intermediate",
                "type": "parallel",
                "skills": skills,
                "nodeIds": [str(tid) for tid in aco_path],
                "steps": steps,
                "convergence": aco.history,
                "cost": round(aco_cost, 2),
                "bridges": len(bridge_id_pairs),
            }]

            topo = kg_combined.learning_order()
            for skill_name in skills:
                only_skill_topics = [
                    t for t in topo
                    if tid_to_info.get(t.topic_id, {}).get("skill") == skill_name
                ]
                paths.append({
                    "id": f"path-{skill_name.lower().replace(' ', '-')}-solo",
                    "name": f"{skill_name} Only",
                    "description": f"Study {skill_name} independently ({len(only_skill_topics)} topics).",
                    "duration": f"{len(only_skill_topics)} topics",
                    "difficulty": "intermediate",
                    "type": "single",
                    "skills": [skill_name],
                    "nodeIds": [str(t.topic_id) for t in only_skill_topics],
                    "steps": [_step(t.topic_id) for t in only_skill_topics],
                })
        t_paths = time.time() - t4

        # 10. Benefits + stats
        if len(skills) == 2:
            benefits = _parallel_benefits(
                bridges,
                per_skill_kg[skills[0]],
                per_skill_kg[skills[1]],
                skills[0],
                skills[1],
            )
        else:
            benefits = {
                "synergy": {
                    "score": round(min(len(bridges) / max(len(merged_spec), 1) * 5, 1.0), 3),
                    "label": "Multi",
                    "description": (
                        f"{len(skills)} skills are being learned together with "
                        f"{len(bridges)} detected cross-skill bridge concept(s)."
                    ),
                },
                "bridges": bridges[:20],
            }

        per_skill_stats = {skill_name: _graph_stats(per_skill_kg[skill_name]) for skill_name in skills}
        stats_combined = _graph_stats(kg_combined)

        elapsed = time.time() - t0
        log.info(
            "generate-parallel  skills=%r  total_topics=%d  bridges=%d  elapsed=%.2fs",
            skills, kg_combined.num_topics, len(bridges), elapsed,
        )

        return jsonify({
            "skills":   skills,
            "skillKey": combined_key,
            "nodes":    nodes,
            "edges":    edges,
            "paths":    paths,
            "bridges":  bridges,
            "benefits": benefits,
            "stats": {
                **per_skill_stats,
                "combined": stats_combined,
            },
            "difficultyScores": {
                str(tid): {
                    "score":    round(score, 4),
                    "domain":   tid_to_info.get(tid, {}).get("domain", "unknown"),
                    "skill":    tid_to_info.get(tid, {}).get("skill", ""),
                    "isBridge": tid in bridge_tids,
                }
                for tid, score in diff_scores.items()
            },
            "elapsed": round(elapsed, 2),
            "timing": {
                "scrape_s":  round(t_scrape, 3),
                "graph_ms":  round(t_graph * 1000, 2),
                "layout_ms": round(t_layout * 1000, 2),
                "diff_ms":   round(t_diff * 1000, 2),
                "paths_ms":  round(t_paths * 1000, 2),
            },
        })

    except Exception as exc:
        log.error("generate-parallel failed: %s\n%s", exc, traceback.format_exc())
        return jsonify({"error": str(exc)}), 500


# ═══════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
