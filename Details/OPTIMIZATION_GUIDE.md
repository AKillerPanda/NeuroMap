# NeuroMap Optimization Guide

## Overview

This guide summarizes optimization decisions for NeuroMap across frontend build, backend runtime, and deployment operations.

---

## Frontend Optimization

### Vite Build Configuration

- Code splitting is enabled for major dependency groups.
- Production minification is enabled.
- CSS code splitting is enabled.
- Source maps are hidden for production output.

### Bundle Analysis

Use the following command to inspect build artifacts:

```bash
cd src/Frontend
npm run build
```

### Performance Best Practices

- Prefer route-level and vendor-level chunking.
- Keep static assets cacheable and immutable when hashed.
- Avoid large synchronous work in initial render paths.

### SEO and Accessibility

- Ensure metadata and social tags are present.
- Use semantic structure and keyboard-accessible controls.
- Keep color contrast and focus states accessible.

---

## Backend Optimization

### Response Compression

- Compression is enabled for API responses.
- This significantly reduces transfer size for JSON payloads.

### Caching Strategy

- In-memory graph cache uses an LRU-style eviction model.
- Dictionary/state initialization is performed at startup where appropriate.

### Threading and Concurrency

- Thread pools are used for parallelizable workloads.
- Per-skill locks protect mutable graph operations.

### Lazy Dependency Loading

- Heavy ML dependencies can be loaded lazily.
- Fallback logic keeps API usable in constrained environments.

### Security Headers

- Security headers are set at API and proxy layers.
- CORS should be restricted to explicit allowed origins.

---

## Data and Storage Notes

### Current Model

- Runtime graph cache in backend memory.
- Persistent user-level graph/topic state in frontend storage.

### Future Direction

- Move long-lived user data to persistent storage.
- Add retention, backup, and observability around state changes.

---

## Deployment Guidance

### Environment Configuration

Use environment variables for operational behavior and secrets.

```env
FLASK_ENV=production
FLASK_DEBUG=0
SECRET_KEY=replace-me
THREAD_POOL_SIZE=4
LOG_LEVEL=INFO
```

### Frontend Production Build

```bash
cd src/Frontend
npm install
npm run build
```

### Backend Production Run

```bash
cd src/Backend
pip install -r requirements.txt
gunicorn -w 4 -b 0.0.0.0:5000 api:app --timeout=60
```

---

## Profiling Checklist

### Frontend

- Run Lighthouse audits for performance/accessibility.
- Validate chunk sizes and caching behavior.

### Backend

- Track endpoint latency (`p50`, `p95`, `p99`).
- Monitor memory growth and cache eviction behavior.
- Log slow operations for graph generation and pathing.

---

## Troubleshooting

### Slow Graph Generation

- Reduce topic count per request.
- Verify backend resource limits.
- Check upstream source latency for scraping-heavy flows.

### High Memory Usage

- Verify cache size constraints.
- Inspect request patterns for repeated large graph loads.

### Large Frontend Build

- Inspect chunk reports.
- Move infrequent features to lazy-loaded boundaries.

### API Timeout Issues

- Verify worker count and request timeout settings.
- Inspect upstream dependencies and long-running handlers.

---

## Maintenance Cadence

- Review dependencies monthly.
- Re-run security scans in CI.
- Revalidate performance baselines after major releases.

---

**Last Updated:** March 2026  
**Version:** 1.1
