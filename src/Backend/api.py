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

import logging
import math
import time
import traceback
import threading
from collections import OrderedDict
from typing import Any

import numpy as np
from flask import Flask, jsonify, request
from flask_cors import CORS

# ── Backend imports ─────────────────────────────────────────────────
from Webscraping import get_learning_spec
from graph import KnowledgeGraph, TopicLevel
from ACO import LearningPathACO
from SDS import spell_correct, correct_phrase, load_dictionary
# difficulty_gnn imports torch eagerly — defer to first use
_predict_difficulty = None
_get_difficulty_explanation = None
_get_smart_recommendation = None

def _ensure_difficulty_gnn():
    global _predict_difficulty, _get_difficulty_explanation, _get_smart_recommendation
    if _predict_difficulty is None:
        from difficulty_gnn import predict_difficulty, get_difficulty_explanation, get_smart_recommendation
        _predict_difficulty = predict_difficulty
        _get_difficulty_explanation = get_difficulty_explanation
        _get_smart_recommendation = get_smart_recommendation

# ── App setup ───────────────────────────────────────────────────────
app = Flask(__name__)
CORS(app)  # allow requests from the Vite dev server

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

def _store_graph(key: str, value: tuple[KnowledgeGraph, list[dict]]) -> None:
    """Thread-safe LRU insert into the graph store."""
    with _graph_lock:
        if key in _graph_store:
            _graph_store.move_to_end(key)
        _graph_store[key] = value
        while len(_graph_store) > _GRAPH_STORE_MAX:
            _graph_store.popitem(last=False)

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
    stats: dict[str, Any] = {
        "numTopics": kg.num_topics,
        "numEdges":  int(kg.build_edge_index().size(1)),
    }
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
    n_edges = stats.get("numEdges", 0)
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

    success = kg.master_topic(tid)
    if not success:
        missing = [
            kg.topics[p].name for p in kg.topics[tid].prerequisites
            if not kg.topics[p].mastered
        ]
        # Return 200 with success=false so the frontend can read the body
        return jsonify({
            "success": False,
            "reason": f"prerequisites not met: {', '.join(missing)}",
            "mastered":  [{"id": str(t.topic_id), "name": t.name} for t in kg.get_mastered()],
            "available": [{"id": str(t.topic_id), "name": t.name} for t in kg.get_available()],
            "locked":    [{"id": str(t.topic_id), "name": t.name} for t in kg.get_locked()],
            "progress":  round(kg.mastery_progress(), 4),
        })

    return jsonify({
        "success":   True,
        "mastered":  [{"id": str(t.topic_id), "name": t.name} for t in kg.get_mastered()],
        "available": [{"id": str(t.topic_id), "name": t.name} for t in kg.get_available()],
        "locked":    [{"id": str(t.topic_id), "name": t.name} for t in kg.get_locked()],
        "progress":  round(kg.mastery_progress(), 4),
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
    positions = kg.spectral_graph_positions()
    
    # Normalize to viewport coords if needed
    positions_normalized = {}
    for tid, (x, y) in positions.items():
        positions_normalized[str(tid)] = [round(float(x), 4), round(float(y), 4)]
    
    return jsonify({
        "positions": positions_normalized,
        "metadata": {
            "method": "spectral_laplacian",
            "eigenvalues": [round(float(v), 4) for v in kg.spectral_eigenvalues(k=3)],
            "algebraicConnectivity": round(kg.algebraic_connectivity(), 4),
        }
    })


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



# ═══════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
