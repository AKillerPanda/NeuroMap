# NeuroMap

NeuroMap is an AI-assisted learning platform that converts a topic into an explorable knowledge graph with prerequisites, learning paths, resources, and progress tracking.

It combines:

- Spectral graph analysis for graph quality and structure
- GNN-based difficulty estimation (with fallback heuristics)
- Ant Colony Optimization (ACO) for path sequencing
- Multi-source resource scraping for practical study links

## Current Product Scope

NeuroMap currently supports two major learning workflows:

1. AI Knowledge Graph mode:

- Generate topic maps from a skill prompt
- Run single-skill or tandem multi-skill generation
- Show node-level difficulty, recommendations, and summaries
- Add generated graphs into the persistent overall NeuroMap

2\. Overall NeuroMap mode:

- Maintain your accumulated topics and relationships
- View an optimized ACO path in the graph view
- Fetch topic resources on click
- Score overall-map topic difficulty through backend inference

## Key Features

- AI graph generation with prerequisite-aware structure
- Tandem multi-skill learning path generation
- Bridge detection across skills for integration opportunities
- Dynamic path optimization via ACO
- Topic mastery state and prerequisite validation
- Resource aggregation including playlist-oriented links
- Overall-map difficulty scoring endpoint for ad-hoc topic sets

## Architecture

Backend:

- Flask API in src/Backend/api.py
- Graph + spectral utilities in src/Backend/graph.py
- Path optimization in src/Backend/ACO.py
- Difficulty model in src/Backend/difficulty_gnn.py
- Scraping + plan assembly in src/Backend/Webscraping.py

Frontend:

- Vite + React + TypeScript app in src/Frontend
- AI graph page in src/Frontend/app/pages/EnhancedGraph.tsx
- Overall map page in src/Frontend/app/pages/Graph.tsx
- Shared topic state in src/Frontend/app/context/TopicsContext.tsx

## Setup

### Backend (Windows PowerShell)

```bash
cd src/Backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python api.py
```

Backend runs at <http://localhost:5000>.

### Frontend

```bash
cd src/Frontend
npm install
npm run dev
```

Frontend runs at <http://localhost:5173> (or the next free Vite port).

## API Quick Reference

Core generation:

- POST /api/generate
- POST /api/generate-parallel
- POST /api/sub-graph

Difficulty and summaries:

- GET /api/difficulty/{skill}
- GET /api/summary/{skill}/{topicId}
- POST /api/overall-difficulty

Pathing and progression:

- GET /api/learning-paths/{skill}
- POST /api/aco-path
- POST /api/master
- POST /api/shortest-path
- GET /api/progress/{skill}

Utilities:

- GET /api/spectral-positions/{skill}
- POST /api/spell-check
- GET /api/health

Example:

```bash
curl -X POST http://localhost:5000/api/generate \
  -H "Content-Type: application/json" \
  -d '{"skill": "Machine Learning"}'
```

## Typical Workflow

1. Generate an AI graph from one or more skills.
2. Inspect node details, summaries, and recommended next topics.
3. Add useful generated nodes into the overall NeuroMap.
4. Use the overall map to track growth and follow ACO path guidance.
5. Open node resources for targeted study material.

## Notes on Difficulty Model

- If torch / model dependencies are unavailable, the backend falls back to heuristic scoring.
- Fallback keeps the app functional, but model-based scoring quality is lower.

## Performance Snapshot

- Graph generation: usually bounded by scraping latency
- Layout and graph analytics: typically tens of milliseconds
- ACO path optimization: typically sub-second for moderate graph sizes

## Documentation

- Backend API guide: src/Backend/API_INTEGRATION.md
- Full integration guide: src/INTEGRATION_GUIDE.md
- Detailed project summary: detailed summary.md

## Contributing

Contributions are welcome.

Recommended contribution areas:

- Better source ranking and trust scoring
- Model quality and calibration improvements
- Persistence, authentication, and collaboration features
- Test coverage and CI hardening

## License

See LICENSE.
