# NeuroMap Quick Reference

## 🟢 One-Command Setup

### Backend
```bash
cd src/Backend && python -m venv venv && \
source venv/Scripts/activate && \
pip install -r requirements.txt && \
python api.py
```

### Frontend
```bash
cd src/Frontend && npm install && npm run dev
```

## 🔌 Core API Routes

### Generate Knowledge Graph
```http
POST /api/generate
Content-Type: application/json

{"skill": "Machine Learning"}
```

**Response:** `{nodes, edges, paths, stats, timing}`

### Get Difficulty Predictions
```http
GET /api/difficulty/Machine%20Learning
```

**Response:** `{difficulties: {...}, recommendations: [...]}`

### Master a Topic
```http
POST /api/master
Content-Type: application/json

{"skill": "ML", "topicId": "5"}
```

**Response:** `{success: boolean, progress: 0-1, available: [...], locked: [...]}`

### Get Spectral Positions
```http
GET /api/spectral-positions/Machine%20Learning
```

**Response:** `{positions: {topicId: [x, y], ...}, metadata: {...}}`

### Other Routes
- `GET /api/learning-paths/{skill}` — All paths
- `POST /api/shortest-path` — Minimal path to target
- `GET /api/progress/{skill}` — Current state
- `POST /api/spell-check` — Fix typos

---

## 📚 File Overview

| File | Role |
|------|------|
| `graph.py` | Spectral KnowledgeGraph, Laplacian, embeddings |
| `api.py` | Flask endpoints, graph storage, LRU cache |
| `ACO.py` | Ant Colony Optimization for paths |
| `difficulty_gnn.py` | GAT model, difficulty prediction |
| `Webscraping.py` | Multi-source resource discovery |
| `EnhancedGraph.tsx` | React component, visualization |
| `API_INTEGRATION.md` | Full API documentation |
| `INTEGRATION_GUIDE.md` | Full-stack architecture guide |

---

## 🎯 Key Concepts (Simplified)

### Spectral Properties
- **Laplacian L = D - A** — captures graph structure globally
- **Fiedler vector λ₂** — cuts graph into 2 optimal clusters
- **λ₂ (algebraic connectivity)** — how connected is the graph (0=disconnected)

### Difficulty Model
- **10 features** per topic (in-degree, depth, Fiedler position, etc.)
- **GAT** — Graph Attention Network learns which features matter
- **Self-supervised** — no labeled training data needed

### ACO Algorithm
- **Ants walk paths** following pheromone + heuristic
- **Pheromone warm-start** from Fiedler distances (smart initialization)
- **Cost = difficulty jumps + weak relatedness** (vectorized)
- **Early stop** after stagnation (5 iterations)

---

## 💡 Common Tasks

### Add New Endpoint
1. Write handler in `api.py`
2. Call backend logic (graph.py, difficulty_gnn.py, etc.)
3. Return `jsonify({...})`

### Update Frontend
1. `EnhancedGraph.tsx` or create new component
2. `useEffect(() => fetch("/api/..."))` to get data
3. Use ReactFlow or ShadCN components for UI

### Debug Slow Graph
1. Check `timing` in `/api/generate` response
2. If `scrape_s` is high → network issue
3. If `graph_ms` is high → graph structure complex
4. If `compute_ms` high → increase `k_max` or reduce topics

---

## 🛡️ Error Messages

| Error | Cause | Fix |
|-------|-------|-----|
| `no graph stored for '...'` | Generate first | POST `/api/generate` |
| `invalid topicId` | Wrong type | Pass as string or int |
| `prerequisites not met` | Not unlocked | Master prereqs first |
| `scraping timeout` | Slow network | Increase `_TIMEOUT` |
| Import torch fails | PyTorch not installed | `pip install torch` |

---

## ⚡ Performance Tips

- **Spectral embedding:** cached — repeated calls are free
- **Graph store:** LRU with 50-entry cap (adjust `_GRAPH_STORE_MAX`)
- **Webscraping:** 4-worker ThreadPoolExecutor (adjust `max_workers`)
- **ACO:** early stop detects convergence (adjust patience threshold)

---

## 🔗 Frontend Example

```typescript
// Fetch graph
const res = await fetch("/api/generate", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ skill: "Python" })
});
const data = await res.json();

// Master a topic
const masterRes = await fetch("/api/master", {
  method: "POST",
  body: JSON.stringify({ skill: "Python", topicId: "5" })
});
const result = await masterRes.json();
console.log(`Progress: ${result.progress * 100}%`);

// Get recommendations
const recRes = await fetch(`/api/difficulty/Python`);
const recs = (await recRes.json()).recommendations;
```

---

## 📊 Ports & URLs

| Service | URL | Env |
|---------|-----|-----|
| Backend | http://localhost:5000 | Flask |
| Frontend | http://localhost:5173 | Vite |
| API Docs | http://localhost:5000 + route | See API_INTEGRATION.md |

---

## 🚀 Deploy to Production

**Backend:**
```bash
# Gunicorn (multiple workers)
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 api:app
```

**Frontend:**
```bash
npm run build
# Serve dist/ folder with any static server
```

---

## 🐛 Debugging

### Print timing
```python
import time
t0 = time.time()
# ... code ...
print(f"Elapsed: {time.time() - t0:.3f}s")
```

### Check graph structure
```python
kg = KnowledgeGraph.from_spec(spec)
print(f"Topics: {kg.num_topics}")
print(f"Edges: {kg.build_edge_index().size(1)}")
print(f"Connectivity: {kg.algebraic_connectivity():.4f}")
```

### View predictions
```python
difficulties = _predict_difficulty(kg)
for tid, score in sorted(difficulties.items()):
    t = kg.topics[tid]
    print(f"{t.name}: {score:.3f}")
```

---

## 📖 Further Reading

- **Spectral Graph Theory:** [Prof. Spielman's Notes](http://cs-www.cs.yale.edu/homes/spielman/sgta/)
- **Graph Attention Networks:** [Veličković et al., 2017](https://arxiv.org/abs/1710.10903)
- **Ant Colony Optimization:** [Dorigo & Stützle, 2004](https://books.google.com/books?id=I3bFSgAACAAJ)
- **PyTorch Geometric:** [Documentation](https://pytorch-geometric.readthedocs.io/)

---

**Happy Hacking! 🧠**
