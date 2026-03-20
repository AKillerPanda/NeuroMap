# NeuroMap Full-Stack Integration Guide

## Project Vision

**NeuroMap** is an AI-powered intelligent learning assistant that transforms any subject into a **dynamic topological knowledge graph**. It reveals:
- **Prerequisite relationships** — what you must learn first
- **Conceptual overlaps** — where disciplines intersect
- **Hierarchical topic structures** — how topics relate at different levels
- **Hidden connections** — unexpected bridges between domains

By leveraging **spectral graph theory** and **AI algorithms**, NeuroMap turns fragmented information into an intuitive, navigable knowledge network.

---

## Architecture

### Backend Stack

```
┌─────────────────────────────────────────────────────────────┐
│                    Flask REST API (api.py)                  │
│  Serves graph, paths, difficulty predictions, spec layout   │
└──────┬──────────────────────────────────────────────────────┘
       ↓
┌──────────────────────┬──────────────────┬─────────────────────┐
│  Webscraping.py      │  graph.py        │  difficulty_gnn.py  │
│  Multi-source        │  Spectral        │  Graph Attention    │
│  resource discovery  │  Laplacian       │  Network (Torch)    │
│  (Wiki, GfG, etc.)   │  embeddings      │  Difficulty predict │
└──────────────────────┴──────────────────┴─────────────────────┘
       │                       │                   │
       └───────────────────────┼───────────────────┘
                               ↓
                      ┌──────────────────┐
                      │  ACO.py          │
                      │  Ant Colony Opt. │
                      │  for learning    │
                      │  path smooth     │
                      │  optimization    │
                      └──────────────────┘
```

### Frontend Stack

```
┌────────────────────────────────────────────────────────────┐
│                  React + TypeScript                        │
├────────────────────────────────────────────────────────────┤
│  EnhancedGraph.tsx  — Spectral layout visualization       │
│  TopicsContext.tsx  — Global graph state management       │
│  LearningPath.tsx   — Path viewer & step-by-step guide    │
│  Home.tsx           — Topic search & entry point          │
├────────────────────────────────────────────────────────────┤
│            ReactFlow (node-edge visualization)            │
│            Tailwind CSS (responsive design)               │
│            ShadCN UI (accessible components)              │
└────────────────────────────────────────────────────────────┘
```

---

## File Structure

```
NeuroMap/
├── src/
│   ├── Backend/
│   │   ├── api.py                  # Flask REST server
│   │   ├── graph.py                # Spectral KnowledgeGraph class
│   │   ├── difficulty_gnn.py       # GAT model for difficulty prediction
│   │   ├── ACO.py                  # Ant Colony Optimization for paths
│   │   ├── Webscraping.py          # Multi-source resource scraping
│   │   ├── SDS.py                  # Spelling correction (if exists)
│   │   ├── API_INTEGRATION.md      # API endpoint documentation
│   │   └── requirements.txt        # Python dependencies
│   │
│   ├── Frontend/
│   │   ├── app/
│   │   │   ├── App.tsx             # Root component
│   │   │   ├── routes.tsx          # React Router config
│   │   │   ├── pages/
│   │   │   │   ├── Home.tsx        # Landing page
│   │   │   │   ├── Graph.tsx       # Original graph viewer
│   │   │   │   ├── EnhancedGraph.tsx  # NEW spectral+GAT visualization
│   │   │   │   ├── LearningPath.tsx   # Path details
│   │   │   │   └── Workspace.tsx      # Topic management
│   │   │   ├── components/
│   │   │   │   ├── ui/             # ShadCN UI components
│   │   │   │   └── figma/          # Custom components
│   │   │   ├── context/
│   │   │   │   └── TopicsContext.tsx # Global graph state
│   │   │   ├── utils/
│   │   │   ├── data/
│   │   │   └── styles/
│   │   └── styles/                 # CSS files (Tailwind, theme)
│   │
│   └── .gitignore                  # Version control ignore rules
│
├── READMe.md                       # Project overview
└── requirements.txt                # Backend dependencies
```

---

## Setup Instructions

### Prerequisites
- Python 3.9+
- Node.js 16+
- pip + npm

### Backend Setup

1. **Create Python virtual environment:**
   ```bash
   cd src/Backend
   python -m venv venv
   source venv/Scripts/activate  # Windows: .\venv\Scripts\activate
   ```

2. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

   **Key packages:**
   ```
   Flask==2.3.0
   flask-cors==4.0.0
   torch>=2.0.0
   torch-geometric>=2.3.0
   scipy>=1.9.0
   numpy>=1.24.0
   beautifulsoup4==4.12.0
   requests==2.31.0
   pandas==2.0.0
   ```

3. **Run the backend server:**
   ```bash
   python api.py
   # Server runs on http://localhost:5000
   ```

### Frontend Setup

1. **Install dependencies:**
   ```bash
   cd src/Frontend
   npm install
   ```

2. **Run the development server:**
   ```bash
   npm run dev
   # Frontend runs on http://localhost:5173
   ```

3. **Build for production:**
   ```bash
   npm run build
   ```

---

## Key Concepts

### Spectral Graph Theory

**NeuroMap** uses the Laplacian matrix to extract global graph properties:

- **Laplacian L = D - A** where D = degree matrix, A = adjacency
- **Eigenvalues λ₀ ≤ λ₁ ≤ ... ≤ λₙ** sorted by magnitude
- **Fiedler vector** (2nd eigenvector) partitions the graph optimally

**Applications:**
- **Spectral embedding** for 2D/3D layouts (E = eigenvectors of smallest eigenvalues)
- **Algebra connectivity λ₂** measures how "connected" the curriculum is
- **Spectral clustering** groups related topics automatically

### Graph Attention Networks (GAT)

The `DifficultyGAT` model predicts how hard each topic is by analyzing:
- **Local features**: in-degree, out-degree, topological depth
- **Global features**: Fiedler position, spectral embedding
- **Temporal features**: what the user has already mastered

**Self-supervised calibration** uses graph structure alone to initialize weights—no external labeled data needed.

### Ant Colony Optimization (ACO)

Finds the optimal learning path by simulating pheromone trails:

1. **Warm start** with Fiedler-based pheromone (spectrally close topics get higher pheromone)
2. **Ants build paths** subject to prerequisite constraints
3. **Cost function** penalizes difficulty jumps and rewards spectral locality
4. **Evaporation + deposit** refine paths over iterations
5. **Convergence detection** stops after 5 stagnant iterations (typically ~100-500ms)

---

## API Quick Reference

### Main Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/generate` | Build full knowledge graph |
| GET | `/api/spectral-positions/{skill}` | Get 2D Fiedler layout |
| GET | `/api/difficulty/{skill}` | Predict difficulty + recommendations |
| GET | `/api/learning-paths/{skill}` | All learning paths |
| POST | `/api/master` | Mark topic as mastered |
| POST | `/api/shortest-path` | Min path to target |
| GET | `/api/progress/{skill}` | Current mastery state |

### Example: Generate a Graph

```bash
curl -X POST http://localhost:5000/api/generate \
  -H "Content-Type: application/json" \
  -d '{"skill": "Machine Learning"}'
```

Response: `{ "skill": "...", "nodes": [...], "edges": [...], "paths": [...], "stats": {...} }`

---

## Frontend Integration

### TopicsContext (Global State)

```typescript
interface TopicsContextType {
  topics: Topic[];
  relations: Relation[];
  skill: string;
  addTopic: (topic: Topic) => void;
  addRelation: (relation: Relation) => void;
  masterTopic: (topicId: string) => Promise<void>;
}

const { topics, relations, skill, masterTopic } = useTopics();
```

### Using EnhancedGraph Component

```typescript
import { EnhancedGraph } from "./pages/EnhancedGraph";

// In router:
{
  path: "/graph/:skill",
  element: <EnhancedGraph />
}

// Usage:
<Link to="/graph/Machine%20Learning">
  View Graph
</Link>
```

### Fetching Data from Backend

```typescript
// Initialize graph
const response = await fetch("/api/generate", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ skill: "Python Programming" })
});
const data = await response.json();

// Master a topic
const masterRes = await fetch("/api/master", {
  method: "POST",
  body: JSON.stringify({ skill, topicId: "5" })
});
const masterData = await masterRes.json();
if (masterData.success) {
  console.log(`Progress: ${masterData.progress * 100}%`);
}

// Get recommendations
const diffRes = await fetch(`/api/difficulty/${skill}`);
const recs = (await diffRes.json()).recommendations;
```

---

## Development Workflow

### Adding a New Feature

1. **Define API endpoint** in `api.py`
2. **Implement backend logic** (graph.py, difficulty_gnn.py, etc.)
3. **Create TypeScript component** in Frontend
4. **Call backend via fetch** in component
5. **Test locally** with npm dev + Flask server
6. **Update documentation**

### Example: Adding a "difficulty heatmap" view

**Backend (api.py):**
```python
@app.route("/api/heatmap/<skill>", methods=["GET"])
def get_heatmap(skill: str):
    entry = _get_graph(skill.lower())
    if not entry:
        return jsonify({"error": "no graph"}), 404
    kg, _ = entry
    difficulties = _predict_difficulty(kg)
    return jsonify({"heatmap": difficulties})
```

**Frontend (EnhancedGraph.tsx):**
```typescript
useEffect(() => {
  fetchHeatmap();
}, [skill]);

const fetchHeatmap = async () => {
  const res = await fetch(`/api/heatmap/${skill}`);
  const data = await res.json();
  // Visualize heatmap
};
```

---

## Performance Tuning

### Backend Optimization

- **Spectral embedding:** O(E) via ARPACK (shift-invert); cached per graph
- **ACO convergence:** Stagnation detection + early stopping (typical 500ms for 25 topics)
- **Webscraping:** Concurrent ThreadPoolExecutor (4 workers) reduces ~8s to ~2s

### Frontend Optimization

- **ReactFlow:** Use `fitView` sparingly (expensive layout recalc)
- **State management:** Keep graph state in Context, avoid re-renders with useCallback
- **Network:** Batch API calls (fetch all at once rather than cascading)

---

## Troubleshooting

### Issue: Import torch fails
**Solution:** Install PyTorch for your platform:
```bash
pip install torch torchvision torchaudio
pip install torch_geometric
```

### Issue: Flask CORS errors
**Solution:** CORS is enabled in api.py via `CORS(app)`. Ensure frontend & backend ports are different.

### Issue: Graph generation is slow
**Solution:** 
- Increase scraping timeout (in Webscraping.py: `_TIMEOUT`)
- Check network connectivity
- For large topics, ACO may need more time—adjust `k_max` or `time_limit`

### Issue: Difficulty predictions are all zeros
**Solution:** Model hasn't been calibrated yet. Call `/api/difficulty/{skill}` which triggers calibration on first use.

---

## Future Enhancements

1. **User accounts & persistent progress** — Save mastery state to database
2. **Social learning** — Leaderboards, shared paths, peer discussions
3. **Adaptive difficulty** — Personalize difficulty based on mastery rate
4. **Curriculum generation** — Let users create custom curricula
5. **Export to formats** — PDF learning plans, Anki flashcard decks
6. **Real-time collaboration** — Multiple users studying together

---

## Questions?

For questions or contributions, please open an issue on GitHub or reach out to the maintainers.

**Happy Learning! 🧠**
