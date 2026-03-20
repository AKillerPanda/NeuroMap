# NeuroMap: Intelligent Learning Assistant

**Transform any subject into a dynamic topological knowledge graph.**

NeuroMap is an AI-powered platform that automatically generates a structured map showing how concepts interconnect. Instead of learning topics in isolation, NeuroMap reveals:

- **Prerequisite relationships** — what you must learn first
- **Conceptual overlaps** — where disciplines intersect  
- **Hierarchical topic structures** — how topics relate at different levels
- **Hidden connections** — unexpected bridges between domains

By leveraging **spectral graph theory**, **Graph Attention Networks**, and **Ant Colony Optimization**, NeuroMap turns fragmented information into an intuitive, navigable knowledge network, making learning more efficient, contextual, and engaging.

---

## 🚀 Key Features

### Intelligent Knowledge Graph
- **Spectral Laplacian Embedding** — Uses eigenvectors of the graph Laplacian for optimal 2D layout
- **Topological Analysis** — Computes algebraic connectivity, spectral gap, and graph partitions
- **Automatic Resource Discovery** — Scrapes Wikipedia, GeeksforGeeks, GitHub, and more
- **Hierarchical Prerequisite Structure** — Ensures you never hit a knowledge gap

### AI-Powered Learning Paths
- **Graph Attention Networks (GAT)** — Predicts per-topic difficulty with plain-English explanations
- **Ant Colony Optimization** — Finds smooth learning curves that minimize cognitive load
- **Multiple Path Options** — Complete / Optimal (ACO) / Quick Start variants
- **Real-time Mastery Tracking** — Prerequisites validated as you progress

### Curriculum Insights
- **Curriculum Cohesion** — How tightly interconnected topics are (λ₂ algebraic connectivity)
- **Bottleneck Risk** — Identifies topics that act as gatekeepers
- **Prerequisite Load** — Warns of overly sequential or branch-heavy curricula
- **Learning Shape** — Shows whether the curriculum is Deep, Balanced, or Broad

---

## 🏗️ Architecture

### Backend (Python)
- **Flask REST API** — Lightweight, CORS-enabled HTTP server
- **Spectral Graph Theory** (`graph.py`) — Laplacian eigenvalues, Fiedler vector, embedding
- **Difficulty Prediction** (`difficulty_gnn.py`) — Self-supervised GAT model
- **Learning Path Optimization** (`ACO.py`) — Vectorised Ant Colony algorithm
- **Multi-source Scraping** (`Webscraping.py`) — Concurrent resource discovery

### Frontend (React + TypeScript)
- **ReactFlow** — Interactive node-edge graph visualization  
- **Tailwind CSS** — Responsive, modern design
- **ShadCN UI** — Accessible component library
- **EnhancedGraph.tsx** — Spectral layout viewer + mastery tracker

---

## 📋 Quick Start

### Backend Setup
```bash
cd src/Backend
python -m venv venv
source venv/Scripts/activate          # Windows: .\venv\Scripts\activate
pip install -r requirements.txt
python api.py                          # Runs on http://localhost:5000
```

### Frontend Setup
```bash
cd src/Frontend
npm install
npm run dev                            # Runs on http://localhost:5173
```

### Use It
1. Open http://localhost:5173 in your browser
2. Enter a topic (e.g., "Machine Learning")
3. NeuroMap automatically generates the graph
4. Click topics to master them — prerequisites validated in real time
5. View learning paths and get personalized recommendations

---

## 🔗 API Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/generate` | Build full knowledge graph |
| GET | `/api/spectral-positions/{skill}` | Get 2D Fiedler layout |
| GET | `/api/difficulty/{skill}` | Difficulty predictions + recommendations |
| GET | `/api/learning-paths/{skill}` | All learning paths |
| POST | `/api/master` | Mark topic as mastered |
| POST | `/api/shortest-path` | Minimal path to target |
| GET | `/api/progress/{skill}` | Current mastery state |

**Example:**
```bash
curl -X POST http://localhost:5000/api/generate \
  -H "Content-Type: application/json" \
  -d '{"skill": "Python Programming"}'
```

See [API_INTEGRATION.md](src/Backend/API_INTEGRATION.md) for detailed documentation.

---

## 📊 Technical Highlights

### Spectral Graph Theory
- Uses **Laplacian matrix** for global connectivity analysis
- Computes **Fiedler vector** (2nd eigenvector) for optimal graph bipartition
- **Algebraic connectivity** λ₂ indicates curriculum tightness
- **Spectral clustering** auto-groups related topics

### Graph Attention Networks
- **10 structural features** per topic (in-degree, depth, level, etc.)
- **Self-supervised calibration** — no labeled training data needed
- Generates **plain-English explanations** for each difficulty score

### Ant Colony Optimization
- **Anti-entropy search** with pheromone warm-start
- **Vectorized NumPy** operations (100-500ms for typical graphs)
- **Fiedler-distance heuristic** keeps related topics adjacent
- **Early convergence detection** via stagnation threshold

---

## 🎯 Use Cases

- **Self-Directed Learners** — Create custom curricula for any topic
- **Educators** — Visualize prerequisite chains and identify gaps
- **Career Changers** — Structured roadmaps to new skills
- **Students** — Understand how concepts interconnect
- **Researchers** — Analyze knowledge graph properties

---

## 📈 Performance

- **Graph Generation:** ~2-3 seconds (mostly web scraping)
- **Spectral Layout:** <50ms
- **Difficulty Prediction:** <100ms
- **ACO Optimization:** ~500ms (25 topics)
- **Total End-to-End:** <4 seconds for typical topics

---

## 📚 Documentation

- [Backend API Integration Guide](src/Backend/API_INTEGRATION.md)
- [Full Stack Integration Guide](src/INTEGRATION_GUIDE.md)
- [Graph Theory Background](#)
- [GAT Model Details](#)
- [ACO Algorithm](#)

---

## 🛠️ Tech Stack

**Backend:**
- Flask, PyTorch, PyTorch Geometric
- SciPy (sparse matrices, eigenvalue decomposition)
- BeautifulSoup, Requests (web scraping)
- NumPy (vectorized linear algebra)

**Frontend:**
- React 18, TypeScript, React Router
- ReactFlow (graph visualization)
- Tailwind CSS, ShadCN UI
- Vite (build tool)

---

## 📝 License

This project is open source. See LICENSE for details.

---

## 🤝 Contributing

Contributions welcome! Areas for improvement:
- User accounts & persistent storage
- Social features (shared learning paths, leaderboards)
- Additional cursors (Khan Academy, Coursera, etc.)
- Mobile app
- Real-time collaboration

Please open an issue or PR.

---

## 👁️ Vision Statement

*NeuroMap reimagines how humans learn by making knowledge interconnections visible and navigable. By automating curriculum design through AI, we empower learners to understand not just **what** to learn, but **why** and **in what order**, turning study into an intuitive journey through a living knowledge network.*

---

**Happy Learning! 🧠**
