# NeuroMap Backend API Integration

## Scope

This document describes the core API endpoints used by the frontend for graph generation, analysis, and progression.

---

## Base Information

- Base URL (dev): `http://localhost:5000`
- API prefix: `/api`
- Content type: `application/json`

---

## Endpoint Summary

### Health

- `GET /api/health`
- Purpose: service health/status.

### Single-Skill Graph

- `POST /api/generate`
- Purpose: generate one skill graph.

Request:

```json
{
  "skill": "Machine Learning"
}
```

### Multi-Skill Graph

- `POST /api/generate-parallel`
- Purpose: generate merged graph for 2+ skills.

Request:

```json
{
  "skills": ["Machine Learning", "Statistics"]
}
```

### Difficulty

- `GET /api/difficulty/{skill}`
- Purpose: return difficulty map and recommendations.

### Summaries

- `GET /api/summary/{skill}/{topicId}`
- Purpose: return topic explanation/resources.

### Learning Paths

- `GET /api/learning-paths/{skill}`
- `POST /api/aco-path`
- Purpose: return generated path sequences.

### Mastery and Progress

- `POST /api/master`
- `GET /api/progress/{skill}`
- Purpose: mastery updates and progress retrieval.

### Enrichment and Utility

- `POST /api/sub-graph`
- `POST /api/spell-check`
- `GET /api/spectral-positions/{skill}`

---

## Typical Response Shapes

### Graph Response (Simplified)

```json
{
  "nodes": [],
  "edges": [],
  "paths": [],
  "stats": {}
}
```

### Difficulty Response (Simplified)

```json
{
  "difficulties": {},
  "recommendations": []
}
```

### Error Response

```json
{
  "error": "message"
}
```

---

## Frontend Consumption Notes

- Single route: `/graph/:skill` -> calls `/api/generate`.
- Multi route: `/graph-multi/:skills` -> calls `/api/generate-parallel`.
- Saved graph metadata is persisted client-side for reopening full graph views.

---

## Reliability Notes

- Backend uses in-memory graph caching with bounded size.
- Health endpoint for container orchestration is `/api/health`.
- For production, run via Gunicorn behind Nginx.

---

## Quick Test Commands

```bash
curl http://localhost:5000/api/health
curl -X POST http://localhost:5000/api/generate -H "Content-Type: application/json" -d '{"skill":"Calculus"}'
curl -X POST http://localhost:5000/api/generate-parallel -H "Content-Type: application/json" -d '{"skills":["Calculus","Physics"]}'
```

---

**Last Updated:** March 2026
