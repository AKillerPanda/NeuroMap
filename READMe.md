# NeuroMap

NeuroMap is an AI-assisted learning platform that turns one or more skills into interactive knowledge graphs, optimized learning paths, and an evolving personal map of mastered topics.

## What NeuroMap Does

- Generates single-skill AI knowledge graphs.
- Generates merged multi-skill graphs with cross-domain bridge concepts.
- Scores topic difficulty (GNN when available, heuristic fallback otherwise).
- Produces optimized learning order with Ant Colony Optimization (ACO).
- Lets you save generated graphs into NeuroMap and reopen them later with full graph features.
- Maintains a persistent overall topic map for long-term learning progression.

## Tech Stack

### Frontend Dev Server

- React 18 + TypeScript + Vite
- React Router
- ReactFlow (`@xyflow/react`) for graph rendering
- Tailwind + Radix UI components
- LocalStorage-backed persistent context state

### Backend

- Flask API + Flask-CORS + Flask-Compress
- Graph modeling and spectral analytics
- ACO-based path optimization
- Optional PyTorch-based difficulty model (`difficulty_gnn.py`)
- Multi-source topic/resource scraping

### Deployment

- Docker + Docker Compose
- Nginx frontend serving + `/api` reverse proxy to Flask/Gunicorn

## Project Structure

```text
NeuroMap/
|-- src/
|   |-- Backend/
|   |   |-- api.py                 # Flask API and orchestration layer
|   |   |-- graph.py               # KnowledgeGraph + spectral/topological ops
|   |   |-- ACO.py                 # Learning path optimization algorithms
|   |   |-- difficulty_gnn.py      # Difficulty model support (with fallback integration)
|   |   |-- Webscraping.py         # Topic/resource scraping pipeline
|   |   |-- SDS.py                 # Spelling/dictionary support
|   |   |-- requirements.txt       # Python dependencies
|   |   `-- API_INTEGRATION.md     # Backend API contract docs
|   |
|   |-- Frontend/
|   |   |-- app/
|   |   |   |-- pages/
|   |   |   |   |-- Workspace.tsx       # Topic input, AI generation, merge builder, workspace hub
|   |   |   |   |-- EnhancedGraph.tsx   # AI graph viewer (single + merged)
|   |   |   |   |-- Graph.tsx           # Persistent overall NeuroMap + hub panels
|   |   |   |   `-- LearningPath.tsx    # Learning path page
|   |   |   |-- context/
|   |   |   |   `-- TopicsContext.tsx   # Persistent topic/relation/saved-graph state
|   |   |   `-- routes.tsx              # Route map
|   |   |-- package.json
|   |   `-- vite.config.ts
|   |
|   `-- INTEGRATION_GUIDE.md
|
|-- Dockerfile.backend
|-- Dockerfile.frontend
|-- docker-compose.yml
|-- nginx.conf
`-- READMe.md
```

## Architecture Overview

### 1. AI Graph Generation Flow

1. User enters skill(s) in Workspace.
1. Frontend routes to:
   - `/graph/:skill` for single skill.
   - `/graph-multi/:skills` for merged graph.
1. `EnhancedGraph` requests backend generation:
   - `POST /api/generate`
   - `POST /api/generate-parallel`
1. Backend returns nodes, edges, paths, and stats.
1. Frontend enriches with difficulty and summary endpoints, then renders interactive graph.

### 2. Save-to-NeuroMap Flow

1. In `EnhancedGraph`, user clicks **Add to NeuroMap**.
1. `TopicsContext` merges generated nodes/edges into persistent overall map state.
1. A saved-graph entry is recorded (single or merged) with reopenable route metadata.
1. Saved graphs are available from both Workspace Hub and Graph Hub.

### 3. Overall NeuroMap Flow

1. `Graph.tsx` renders persistent user map (`topics` + `relations`).
1. Backend endpoints support additional scoring/path guidance:
   - `POST /api/overall-difficulty`
   - `POST /api/aco-path`
1. User can open saved AI graphs for focused deep dives and return to the overall integrated map.

## Frontend Responsibilities

- `Workspace.tsx`
  - Add manual topics.
  - Build single and merged AI graphs.
  - Show Saved Graphs and Learning Guide hub.
- `EnhancedGraph.tsx`
  - Render generated AI graph.
  - Topic detail panel (summary/resources/difficulty/mastery).
  - Save graph into NeuroMap.
- `Graph.tsx`
  - Render persistent integrated map.
  - Show saved graph list and guided next-step panel.
- `TopicsContext.tsx`
  - Owns app-wide persistent state:
    - Topics
    - Relations
    - Saved graphs

## Backend Responsibilities

- `api.py`
  - API contract, orchestration, response shaping.
  - Health, generation, summary, progress, difficulty, and utility endpoints.
- `graph.py`
  - Graph primitives, spectral/topological operations, analytics helpers.
- `ACO.py`
  - Path generation and start-candidate logic.
- `difficulty_gnn.py`
  - Difficulty model support used when ML dependencies are available.
- `Webscraping.py`
  - Topic/resource discovery pipeline.

## API Surface (Core)

### Generation

- `POST /api/generate`
- `POST /api/generate-parallel`
- `POST /api/sub-graph`

### Difficulty and Summaries

- `GET /api/difficulty/{skill}`
- `GET /api/summary/{skill}/{topicId}`
- `POST /api/overall-difficulty`

### Learning and Progress

- `GET /api/learning-paths/{skill}`
- `POST /api/aco-path`
- `POST /api/master`
- `POST /api/shortest-path`
- `GET /api/progress/{skill}`

### Utilities

- `GET /api/spectral-positions/{skill}`
- `POST /api/spell-check`
- `GET /api/health`

## Local Development

### Backend (PowerShell)

```bash
cd src/Backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python api.py
```

Backend: `http://localhost:5000`

### Frontend

```bash
cd src/Frontend
npm install
npm run dev
```

Frontend: `http://localhost:5173`

## Docker Deployment

```bash
docker compose up -d --build
```

Health checks:

- Frontend: `http://localhost/health`
- Backend: `http://localhost:5000/api/health`

Note: `docker-compose.yml` requires `SECRET_KEY` to be set in environment or `.env`.

## How Learning Progression Works

- AI graphs provide focused study plans per skill or merged skill set.
- Saved graphs preserve those focused views for later reuse.
- NeuroMap aggregates all added topics and relationships over time.
- Combined use of single + merged + overall map supports both depth and cross-domain transfer learning.

## Related Documentation

- [src/Backend/API_INTEGRATION.md](src/Backend/API_INTEGRATION.md)
- [src/INTEGRATION_GUIDE.md](src/INTEGRATION_GUIDE.md)
- [detailed summary.md](detailed%20summary.md)
- [Details/OPTIMIZATION_REPORT.md](Details/OPTIMIZATION_REPORT.md)
- [Details/OPTIMIZATION_GUIDE.md](Details/OPTIMIZATION_GUIDE.md)
- [Details/DEPLOYMENT_CHECKLIST.md](Details/DEPLOYMENT_CHECKLIST.md)

## License

See [LICENSE](LICENSE).
