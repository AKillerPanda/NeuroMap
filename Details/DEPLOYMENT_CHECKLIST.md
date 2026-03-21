# Production Deployment Checklist

## Pre-Deployment

### Code Quality
- [ ] Run TypeScript strict mode check: `npx tsc --noEmit`
- [ ] Lint Python code: `cd src/Backend && python -m flake8 . --max-line-length=120 --ignore=E501,W503`
- [ ] All tests passing
- [ ] No console errors in browser

### Security
- [ ] Remove debug logging statements
- [ ] Set `FLASK_DEBUG=0` in `.env`
- [ ] Generate strong `SECRET_KEY` in `.env`
- [ ] Review CORS origins (restrict to specific domains)
- [ ] Enable HTTPS in production
- [ ] Run dependency vulnerability scan: `pip-audit` (Python) or `npm audit` (frontend)
- [ ] Run secrets detection: scan for hardcoded credentials/API keys in code and git history
- [ ] Validate required environment variables: ensure `SECRET_KEY`, `FLASK_DEBUG=0`, `FLASK_ENV=production` are set

### Performance
- [ ] Frontend bundle size optimized
- [ ] Backend response times acceptable
- [ ] Database indexes in place (if using external DB)
- [ ] Caching headers configured

## Deployment Steps

### Backend Deployment

1. **Install Dependencies**
```bash
cd src/Backend
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
```

2. **Configure Environment**
```bash
cp .env.example .env
# Edit .env with production values
```

3. **Test Locally**
```bash
python api.py
# Verify all endpoints respond with 200
```

4. **Deploy with Gunicorn**
```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 api:app --timeout=60 --access-logfile -
```

5. **Setup Reverse Proxy (Nginx)**
```nginx
upstream neuromap_backend {
    server 127.0.0.1:5000;
}

server {
    listen 443 ssl http2;
    server_name api.neuromap.example.com;
    
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    
    location / {
        proxy_pass http://neuromap_backend;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;
        proxy_request_buffering off;
    }
}
```

### Frontend Deployment

1. **Build for Production**
```bash
cd src/Frontend
npm install
npm run build
# Creates dist/ folder with optimized assets
```

2. **Deploy to Static Host (e.g., Netlify, Vercel, S3)**
- Upload `dist/` contents
- Configure API endpoint in environment
- **Enable SPA routing**: Client-side routing requires all non-asset routes to redirect to `index.html`
  - Netlify: Use `_redirects` file with catch-all rule: `/* /index.html 200`
  - Vercel: Add rewrite rule in `vercel.json` to fallback non-asset routes to `index.html`
  - S3/CloudFront: Configure CloudFront error handling to serve `index.html` for 404 responses
- Enable compression at CDN level

3. **Configure CORS Headers**
Frontend and backend must have matching CORS configuration:
```python
# Backend - api.py
CORS(app, origins=["https://neuromap.example.com"])
```

### Docker Deployment

**Backend Dockerfile:**
```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY src/Backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY src/Backend .

ENV FLASK_ENV=production
EXPOSE 5000

CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "api:app", "--timeout=60"]
```

**Frontend Dockerfile:**
```dockerfile
FROM node:18-alpine as builder
WORKDIR /app
COPY src/Frontend/package*.json .
RUN npm ci
COPY src/Frontend .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/nginx.conf
RUN mkdir -p /var/run/nginx /var/cache/nginx /var/log/nginx && \
    chown -R nginx:nginx /usr/share/nginx/html /var/run/nginx /var/cache/nginx /var/log/nginx
USER nginx
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

## Post-Deployment

### Verification
- [ ] Backend API responding to requests
- [ ] Frontend loads without errors
- [ ] Graph generation working
- [ ] Spell-check responsive
- [ ] All API endpoints returning proper status codes

### Monitoring
1. **Setup Logging**
   - Centralize logs (CloudWatch, ELK, Datadog)
   - Monitor error rates
   - Alert on timeouts

2. **Performance Monitoring**
   - Track response times
   - Monitor memory usage
   - Track error rates

3. **Uptime Monitoring**
   - Setup health checks every 5 minutes
   - Alert on downtime
   - Track SLA metrics

### Backup and Disaster Recovery

1. **Backup Strategy**
   - [ ] **Frequency**: Automated daily full backups + hourly incremental snapshots
   - [ ] **Database Backups**: If migrating to persistent storage (Cosmos DB, PostgreSQL), enable automated backups
   - [ ] **Cross-Region Replication**: Store backup copies in different geographic regions for resilience
   - [ ] **Encryption**: Ensure all backups are encrypted at rest and in transit
   - [ ] **Retention Policy**: Define retention (e.g., daily for 7 days, weekly for 4 weeks, monthly for 1 year)
   - [ ] **Test Backup Integrity**: Validate backup files monthly to ensure they are recoverable

2. **Recovery Procedures**
   - [ ] **RTO (Recovery Time Objective)**: Target = 1 hour (define acceptable downtime)
   - [ ] **RPO (Recovery Point Objective)**: Target = 15 minutes (define acceptable data loss)
   - [ ] **Step-by-Step Restore Process**: Document how to restore from backup in runbook
   - [ ] **Quarterly DR Drill**: Schedule and execute full recovery test at least quarterly
   - [ ] **Offline Recovery Docs**: Maintain printable recovery documentation in case systems are unavailable
   - [ ] **Failover Automation**: Implement automated failover to standby region if primary is down

3. **Data Integrity Checks**
   - [ ] **Backup Verification Scripts**: Checksum verification, test restore to isolated environment
   - [ ] **Monitoring Alerts**: Configure alerts for backup failures, corrupted backups, or failed integrity checks
   - [ ] **Regular Audits**: Monthly audit of backup logs and recovery success rates

### Scaling Considerations

**Horizontal Scaling:**
- Run multiple gunicorn workers
- Use load balancer (Nginx, HAProxy)
- Consider Kubernetes for container orchestration

**Vertical Scaling:**
- Increase thread pool size in `.env`
- Add more workers to gunicorn
- Upgrade hardware (CPU, RAM)

**Database Scaling (Future):**
- Migrate to persistent storage (Cosmos DB, MongoDB, PostgreSQL)
- Implement distributed caching (Redis)
- Shard graphs by user/org

## Rollback Plan

1. Keep previous version tagged in git
2. Document breaking changes in each release
3. Test rollback procedure regularly
4. Maintain database migration scripts

## Monitoring Dashboards

Create dashboards to track:
- Request latency (p50, p95, p99)
- Error rate
- Memory usage
- CPU usage
- Graph generation time
- API endpoint availability

## Emergency Contacts

- DevOps Lead: [Your Name] — Role: Infrastructure & Deployments — Email: devops@yourdomain.com — Phone: +1-XXX-XXX-XXXX
- Backend Dev: [Your Name] — Role: Backend API & Database — Email: backend@yourdomain.com — Slack: @backend-dev
- Frontend Dev: [Your Name] — Role: Frontend & UX — Email: frontend@yourdomain.com — Slack: @frontend-dev

---

**Last Updated:** March 2026
**Version:** 1.0
