# Production Deployment Checklist

## Pre-Deployment

### Code Quality

- [ ] Run TypeScript strict mode check: `npx tsc --noEmit`
- [ ] Lint Python code: `cd src/Backend && python -m flake8 . --max-line-length=120 --ignore=E501,W503`
- [ ] Ensure all tests are passing.
- [ ] Confirm no browser console errors in core flows.

### Security

- [ ] Disable debug mode (`FLASK_DEBUG=0`).
- [ ] Set a strong `SECRET_KEY`.
- [ ] Restrict CORS to explicit origins.
- [ ] Enable HTTPS at the edge.
- [ ] Run dependency scans (`pip-audit`, `npm audit`).
- [ ] Verify no secrets are committed.

### Performance

- [ ] Verify frontend build size and chunking.
- [ ] Verify backend response-time targets.
- [ ] Confirm caching and compression settings are active.

## Deployment Steps

### Backend Deployment

1. **Install dependencies**

```bash
cd src/Backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

1. **Configure environment**

```bash
cp .env.example .env
# Edit .env with production values
```

1. **Smoke test locally**

```bash
python api.py
# Verify key endpoints respond successfully
```

1. **Run with Gunicorn**

```bash
gunicorn -w 4 -b 0.0.0.0:5000 api:app --timeout=60 --access-logfile -
```

### Frontend Deployment

1. **Build for production**

```bash
cd src/Frontend
npm install
npm run build
```

1. **Deploy static assets**

- Deploy `dist/` to your static host.
- Configure SPA fallback to `index.html`.
- Ensure API requests route to backend `/api/*`.

### Docker Deployment

1. **Build and start stack**

```bash
docker compose up -d --build
```

1. **Verify service health**

```bash
docker compose ps
curl http://localhost/health
curl http://localhost:5000/api/health
```

## Post-Deployment

### Verification

- [ ] Frontend loads successfully.
- [ ] Backend API responds on `/api/health`.
- [ ] Graph generation, spell-check, and path flows work end to end.
- [ ] Saved graph open/remove actions work in Workspace and View Graph.

### Monitoring

- [ ] Centralize logs.
- [ ] Track latency, error rate, memory, and CPU.
- [ ] Add uptime checks and alerting.

## Backup and Disaster Recovery

### Backup Strategy

- [ ] Daily full backups and frequent incremental snapshots.
- [ ] Encrypted backups at rest and in transit.
- [ ] Retention policy documented and enforced.
- [ ] Monthly backup integrity verification.

### Recovery Procedures

- [ ] Define and document RTO/RPO.
- [ ] Keep a tested restore runbook.
- [ ] Execute quarterly disaster recovery drills.

## Rollback Plan

1. Keep previous release images/tags.
1. Document release-level breaking changes.
1. Rehearse rollback and validate data compatibility.

## Operational Dashboards

Track at minimum:

- Request latency (`p50`, `p95`, `p99`).
- Error rate.
- Memory and CPU usage.
- Graph generation time distribution.
- API availability.

---

**Last Updated:** March 2026  
**Version:** 1.1
