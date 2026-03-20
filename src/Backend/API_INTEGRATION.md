# NeuroMap Backend API Integration Guide

## Overview

NeuroMap transforms any topic into a **topological spectral knowledge graph** using:
- **Spectral graph theory** (Laplacian eigenvectors, Fiedler vector)
- **Graph Attention Networks** (GAT) for difficulty prediction
- **Ant Colony Optimization** (ACO) for smooth, cognitively-optimized learning paths
- **Web scraping** (Wikipedia, GeeksforGeeks, GitHub) for resource discovery

## Architecture

```
User Query (topic)
    ↓
Webscraping.py: Extract learning steps + resources (concurrent multi-source)
    ↓
graph.py: Build KnowledgeGraph with spectral properties
    ↓
difficulty_gnn.py: Predict per-topic difficulty (GAT model)
    ↓
ACO.py: Find optimal learning path (smooth difficulty curve)
    ↓
api.py: Serve as REST endpoints for frontend
    ↓
Frontend: Visualize spectral layout + interactive mastery tracking
```

## API Endpoints

### 1. **POST /api/generate** — Main Entry Point
Generates a complete knowledge graph for any topic.

**Request:**
```json
{
  "skill": "Machine Learning"
}
```

**Response:**
```json
{
  "skill": "Machine Learning",
  "nodes": [
    {
      "id": "0",
      "type": "input",
      "position": {"x": 500, "y": 0},
      "data": {
        "label": "Linear Algebra",
        "level": "foundational",
        "difficulty": "beginner",
        "description": "...",
        "mastered": false,
        "prerequisites": [],
        "unlocks": ["Statistics", "Python Basics"],
        "depth": 0,
        "stepIndex": 0,
        "cluster": 0,
        "resources": [
          {
            "title": "Linear Algebra Fundamentals",
            "url": "https://...",
            "source": "wikipedia",
            "type": "article"
          }
        ],
        "estimatedMinutes": 45
      }
    },
    ...
  ],
  "edges": [
    {
      "id": "e0-1",
      "source": "0",
      "target": "1",
      "animated": false,
      "markerEnd": {...}
    },
    ...
  ],
  "paths": [
    {
      "id": "path-full",
      "name": "Complete Path",
      "description": "Master all 8 topics...",
      "duration": "8 topics",
      "difficulty": "advanced",
      "nodeIds": ["0", "1", "2", ...],
      "steps": [
        {
          "topicId": "0",
          "name": "Linear Algebra",
          "level": "foundational",
          "requires": [],
          "unlocks": ["Statistics", "Python Basics"],
          "reason": "Start here — no prerequisites needed"
        },
        ...
      ]
    },
    ...
  ],
  "stats": {
    "numTopics": 8,
    "numEdges": 9,
    "algebraicConnectivity": 1.2345,
    "spectralGap": 0.5678,
    "connectedComponents": 1,
    "avgOutDegree": 1.13,
    "avgInDegree": 1.13,
    "maxOutDegree": 3,
    "maxInDegree": 3,
    "insights": {
      "curriculumCohesion": {
        "rating": "Strong",
        "description": "Topics are tightly interconnected...",
        "value": 1.2345
      },
      "bottleneckRisk": {...},
      "prerequisiteLoad": {...},
      "curriculumShape": {...}
    }
  },
  "elapsed": 2.34,
  "timing": {
    "scrape_s": 1.2,
    "graph_ms": 5.5,
    "layout_ms": 10.3,
    "edges_ms": 1.2,
    "paths_ms": 15.8,
    "stats_ms": 8.9,
    "compute_ms": 41.7
  }
}
```

### 2. **GET /api/spectral-positions/{skill}** — Topological Layout
Returns 2D spectral embedding positions (Fiedler vector-based) for graph visualization.

**Request:**
```
GET /api/spectral-positions/Machine%20Learning
```

**Response:**
```json
{
  "positions": {
    "0": [0.123, -0.456],
    "1": [-0.234, 0.567],
    "2": [0.789, 0.012],
    ...
  },
  "metadata": {
    "method": "spectral_laplacian",
    "eigenvalues": [0.0, 0.1234, 0.5678],
    "algebraicConnectivity": 0.1234
  }
}
```

### 3. **GET /api/difficulty/{skill}** — GAT-based Difficulty Prediction
Predicts per-topic difficulty and recommends next steps.

**Request:**
```
GET /api/difficulty/Machine%20Learning
```

**Response:**
```json
{
  "difficulties": {
    "0": 0.15,
    "1": 0.42,
    "2": 0.78,
    ...
  },
  "recommendations": [
    {
      "id": "5",
      "name": "Statistics",
      "difficulty": 0.35,
      "reason": "Ready after mastering Linear Algebra. This builds your probability intuition for ML."
    },
    ...
  ]
}
```

### 4. **GET /api/learning-paths/{skill}** — All Paths
Returns all pre-computed learning paths (Full, Optimal ACO, Quick Start).

**Request:**
```
GET /api/learning-paths/Machine%20Learning
```

**Response:**
```json
{
  "paths": [
    {
      "id": "path-full",
      "name": "Complete Path",
      "description": "Master all 8 topics in prerequisite order...",
      "duration": "8 topics",
      "difficulty": "advanced",
      "nodeIds": ["0", "1", "2", ...],
      "convergence": [100.0, 95.5, 92.1, ...],
      "steps": [...]
    },
    ...
  ],
  "totalTopics": 8
}
```

### 5. **POST /api/master** — Mark Topic as Mastered
Tracks user progress with prerequisite validation.

**Request:**
```json
{
  "skill": "Machine Learning",
  "topicId": "3"
}
```

**Response (success):**
```json
{
  "success": true,
  "mastered": [
    {"id": "0", "name": "Linear Algebra"},
    {"id": "1", "name": "Python Basics"},
    ...
  ],
  "available": [
    {"id": "3", "name": "Statistics"}
  ],
  "locked": [
    {"id": "5", "name": "Machine Learning"}
  ],
  "progress": 0.375
}
```

**Response (missing prerequisites):**
```json
{
  "success": false,
  "reason": "prerequisites not met: Linear Algebra, Python Basics",
  "mastered": [...],
  "available": [...],
  "locked": [...],
  "progress": 0.25
}
```

### 6. **POST /api/shortest-path** — Minimal Path to Target
Find the minimum topics needed to unlock a target topic.

**Request:**
```json
{
  "skill": "Machine Learning",
  "targetId": "6"
}
```

**Response:**
```json
{
  "path": [
    {"id": "0", "name": "Linear Algebra", "mastered": false, "level": "foundational"},
    {"id": "1", "name": "Statistics", "mastered": false, "level": "intermediate"},
    {"id": "6", "name": "Deep Learning", "mastered": false, "level": "advanced"}
  ]
}
```

### 7. **POST /api/spell-check** — Correct Typos
Fix typos in skill names via Symmetric Delete Spelling (SDS).

**Request:**
```json
{
  "text": "statistcs machne lerning",
  "top_k": 5
}
```

**Response:**
```json
{
  "results": [
    {
      "original": "statistcs",
      "suggestions": [
        {"word": "statistics", "score": 0.94},
        {"word": "statistic", "score": 0.85}
      ],
      "inDictionary": false
    },
    ...
  ]
}
```

### 8. **GET /api/progress/{skill}** — Retrieve Mastery State
Fetch the current progress for a previously-generated graph.

**Request:**
```
GET /api/progress/Machine%20Learning
```

**Response:**
```json
{
  "mastered": [...],
  "available": [...],
  "locked": [...],
  "progress": 0.375
}
```

## Key Features

### Spectral Graph Properties
- **Algebraic Connectivity (λ₂)**: Measures how well-connected the curriculum is (0 = disconnected, ∞ = highly connected)
- **Spectral Gap (λ₂/λ_max)**: Normalized connectivity in [0, 1]; large gap = strong expander-like structure
- **Fiedler Vector**: Optimal 2-way graph partition; used for intelligent node positioning
- **Spectral Clustering**: Groups topics into 3-5 clusters based on structural similarity

### Learning Insights
- **Curriculum Cohesion**: How tightly topics are interconnected (Strong/Moderate/Weak/Disconnected)
- **Bottleneck Risk**: Topics with many prerequisites that may require extra study time
- **Prerequisite Load**: Average number of prerequisites per topic
- **Curriculum Shape**: Whether the learning curve is Deep, Balanced, or Broad

### ACO Optimization
- **Smooth Difficulty Curve**: Minimizes difficulty jumps between consecutive topics
- **Spectral Locality**: Keeps related (spectrally close) topics together
- **Warm Start**: Initializes with Fiedler-distance-based pheromone for faster convergence
- **Early Stopping**: Detects convergence after ~5 stagnant iterations; typical solve time: 100-500ms

### GAT Difficulty Model
- **10 Features**: in-degree, out-degree, depth, level, prerequisite ratio, spectral position (2D), mastery state, neighbourhood effects
- **Self-Supervised**: No external training data; calibrates automatically from graph structure
- **Explainable**: Generates plain-English explanations for each difficulty score

## Frontend Integration Example

### Initialize Graph
```javascript
async function initializeNeuroMap(topic) {
  const response = await fetch("/api/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ skill: topic })
  });
  const data = await response.json();
  return {
    nodes: data.nodes,
    edges: data.edges,
    paths: data.paths,
    stats: data.stats
  };
}
```

### Master a Topic
```javascript
async function masterTopic(skill, topicId) {
  const response = await fetch("/api/master", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ skill, topicId })
  });
  const data = await response.json();
  if (data.success) {
    console.log(`✓ Mastered! Progress: ${(data.progress * 100).toFixed(1)}%`);
  } else {
    console.warn(`✗ ${data.reason}`);
  }
  return data;
}
```

### Get Recommendations
```javascript
async function getRecommendations(skill) {
  const response = await fetch(`/api/difficulty/${skill}`);
  const data = await response.json();
  return data.recommendations.map(r => ({
    topicId: r.id,
    name: r.name,
    difficulty: r.difficulty,
    reason: r.reason
  }));
}
```

## Performance Notes

- **Small graphs** (5-15 topics): ~500ms total (mostly scraping)
- **Medium graphs** (15-40 topics): ~2-3s total
- **Large graphs** (40+ topics): ~5-10s total

Graph computation (build + layout + ACO) is sub-100ms for typical sizes; most time is webscraping.

## Error Handling

- Missing skill: 404 + `{"error": "no graph stored for '...'"}`
- Invalid topic ID: 400 + `{"error": "invalid topicId: ..."}`
- Network timeout during scrape: 504 + `{"error": "scraping timeout"}`

