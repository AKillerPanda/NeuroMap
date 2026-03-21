# NeuroMap Integration Guide

## Purpose

This guide explains how frontend and backend components integrate for graph generation, learning paths, and progress workflows.

---

## Architecture Summary

- Frontend: React + Vite app under `src/Frontend`.
- Backend: Flask API under `src/Backend`.
- Data flow: Frontend calls `/api/*` endpoints and renders graph/path responses.

---

## Core User Flows

### 1. Generate Single-Skill AI Graph

1. User enters one skill on Workspace.
1. Frontend navigates to `/graph/:skill`.
1. EnhancedGraph calls `POST /api/generate`.
1. Frontend requests `GET /api/difficulty/{skill}` and renders enriched nodes.

### 2. Generate Multi-Skill Merged Graph

1. User selects two or more skills.
1. Frontend navigates to `/graph-multi/:skills`.
1. EnhancedGraph calls `POST /api/generate-parallel`.
1. Frontend displays combined graph, bridges, and interleaved paths.

### 3. Add Graph to NeuroMap

1. User clicks **Add to NeuroMap** in EnhancedGraph.
1. Nodes/edges are merged into persistent local NeuroMap state.
1. A saved graph entry is created for later reopening.

### 4. Reopen Saved Graph

1. User opens Saved Graphs in Workspace Hub or NeuroMap Hub.
1. User clicks **Open Graph Tab**.
1. Route opens full EnhancedGraph experience for that graph.

---

## Frontend Integration Points

### Workspace (`src/Frontend/app/pages/Workspace.tsx`)

- Generates single-skill and merged graph routes.
- Shows Saved Graphs and Learning Guide tabs.

### EnhancedGraph (`src/Frontend/app/pages/EnhancedGraph.tsx`)

- Handles both route shapes:
  - `/graph/:skill`
  - `/graph-multi/:skills`
- Fetches graph, difficulty, summary, and mastery data.
- Saves graph metadata into NeuroMap context.

### NeuroMap Graph (`src/Frontend/app/pages/Graph.tsx`)

- Renders persistent overall topic graph.
- Shows Saved Graphs and Learning Guide tabs.
- Reopens saved single and merged AI graphs.

### Shared Context (`src/Frontend/app/context/TopicsContext.tsx`)

- Stores topics, relations, and saved graph entries.
- Persists state to localStorage.

---

## Backend Integration Points

### Graph Generation

- `POST /api/generate` for single-skill graphs.
- `POST /api/generate-parallel` for merged graphs.

### Analysis and Learning

- `GET /api/difficulty/{skill}` for node difficulty and recommendations.
- `GET /api/summary/{skill}/{topicId}` for topic detail panels.
- `GET /api/learning-paths/{skill}` and `POST /api/aco-path` for pathing.

### Progress and Mastery

- `POST /api/master` to mark topic mastered.
- `GET /api/progress/{skill}` for progress metrics.

### Utility

- `POST /api/sub-graph` for topic enrichment.
- `POST /api/spell-check` for input correction.
- `GET /api/health` for health checks.

---

## Deployment Integration Notes

- Frontend expects API at `/api/*`.
- Nginx proxies `/api/*` to backend service.
- Docker compose health checks:
  - Frontend: `http://localhost/health`
  - Backend: `http://localhost:5000/api/health`

---

## Quick Validation Checklist

- [ ] Single-skill graph generation works.
- [ ] Multi-skill graph generation works.
- [ ] Add to NeuroMap persists topics/relations.
- [ ] Saved graph entries appear in both hubs.
- [ ] Open Graph Tab reopens full enhanced view.
- [ ] Health endpoints respond successfully.

---

**Last Updated:** March 2026
