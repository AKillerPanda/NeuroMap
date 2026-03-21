# NeuroMap Detailed Summary

## Executive Summary

NeuroMap has evolved from a single-topic graph prototype into a multi-flow learning platform with:
- AI-generated single-skill and multi-skill knowledge graphs
- Tandem path optimization with cross-domain bridge logic
- Persistent overall NeuroMap aggregation
- Node-level resource enrichment and playlist-focused links
- Difficulty scoring across both AI and overall-map workflows

This document reflects the current implemented state.

## What Is Implemented

### 1. Graph Generation and Analysis

Backend graph capabilities are implemented in src/Backend/graph.py and include:
- DAG-based prerequisite modeling
- Topological depth and ordering utilities
- Spectral operations (Laplacian, Fiedler, clustering, connectivity)
- Helper methods used for analytics, layout, and optimization

### 2. API Layer

The backend Flask API in src/Backend/api.py currently includes:
- Generation endpoints:
  - POST /api/generate
  - POST /api/generate-parallel
  - POST /api/sub-graph
- Difficulty and summary endpoints:
  - GET /api/difficulty/{skill}
  - GET /api/summary/{skill}/{topicId}
  - POST /api/overall-difficulty
- Pathing and progression:
  - GET /api/learning-paths/{skill}
  - POST /api/aco-path
  - POST /api/master
  - POST /api/shortest-path
  - GET /api/progress/{skill}
- Utility endpoints:
  - GET /api/spectral-positions/{skill}
  - POST /api/spell-check
  - GET /api/health

The API also uses in-memory LRU graph storage and per-graph locking for safer concurrent updates.

### 3. Difficulty Scoring

Difficulty scoring is integrated through src/Backend/difficulty_gnn.py with runtime lazy import in src/Backend/api.py.

Current behavior:
- Preferred path: GNN-based difficulty prediction and recommendations
- Fallback path: heuristic scoring when torch/model dependencies are unavailable

The fallback is intentional so the app remains operational in constrained environments.

### 4. Learning Path Optimization

ACO logic in src/Backend/ACO.py supports:
- Standard single-graph path optimization
- Parallel/tandem path optimization with domain-aware bridge behavior
- Dynamic transition shaping for tandem mode:
  - Penalize unrelated cross-domain jumps
  - Encourage foundational coverage in both domains first
  - Delay heavy bridge integration until both domains are warmed up

This aligns tandem sequencing with realistic learner readiness.

### 5. Resource Discovery

Scraping and plan assembly in src/Backend/Webscraping.py supports:
- Multi-source collection (Wikipedia API, GeeksforGeeks, GitHub, DuckDuckGo)
- Playlist-oriented discovery and ranking
- Per-step resource attachment with deduplication

### 6. Frontend Experience

Frontend implementation in src/Frontend includes:
- AI graph page: src/Frontend/app/pages/EnhancedGraph.tsx
  - Graph generation, difficulty retrieval, summaries, mastery actions
  - Add-to-NeuroMap flow for importing generated structures
- Overall map page: src/Frontend/app/pages/Graph.tsx
  - Persistent topic graph visualization
  - Left-side ACO path panel
  - Node click resource retrieval and display
  - Overall-map difficulty score display
- Shared state: src/Frontend/app/context/TopicsContext.tsx
  - Topic and relation persistence
  - AI-import metadata and merge logic

## Data and State Model

Current state model combines:
- Backend ephemeral graph cache for generated skill graphs
- Frontend persistent local topic/relation state for the overall map

This dual-model architecture enables responsive AI generation while preserving user-curated long-term maps.

## Current Limitations

- No persistent database-backed backend state yet
- Model quality depends on local dependency availability
- Scraping quality varies by topic and source response quality
- Full end-to-end automated test coverage is not yet complete

## Recommended Next Milestones

1. Persistence and Identity
- Add backend persistence (user profiles, saved maps, progress history)
- Add authentication and secure sync

2. Reliability and Observability
- Add structured logging and request tracing
- Add endpoint-level integration tests

3. Learning Quality
- Improve bridge detection beyond string similarity
- Introduce confidence-weighted recommendations and ranking

4. Product UX
- Add explainable path mode toggles (difficulty-heavy vs integration-heavy)
- Add export/import formats and collaboration features

## Conclusion

NeuroMap is currently in a strong feature-complete prototype stage for AI-assisted curriculum mapping, with practical path optimization, multi-skill support, and actionable node resources. The next step is production hardening: persistence, testing, and observability.
