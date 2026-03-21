# NeuroMap Performance Optimization Guide

## Overview
This document outlines the optimizations implemented in NeuroMap to ensure production-grade performance, security, and user experience.

## Frontend Optimizations

### 1. **Vite Build Configuration**
- **Code Splitting**: Separate bundles for vendor libraries (ReactFlow, Radix UI, Charts, Router, UI utilities)
- **Minification**: Terser compression with console/debugger removal in production
- **CSS Optimization**: CSS code splitting enabled
- **Source Maps**: Hidden source maps in production (security + bundle size)
- **Lazy Loading**: Components loaded on-demand

### 2. **Bundle Analysis**
Build the project and analyze bundle:
```bash
cd src/Frontend
npm run build
# Bundle size is shown in terminal output
```

### 3. **Performance Best Practices**
- React 18 with concurrent features enabled
- Throttled/debounced event handlers (spell-check uses 260ms debounce)
- Memoized components for expensive renders
- Conditional rendering to avoid DOM pollution
- Efficient state management with React Context

### 4. **Caching Strategy**
- Static assets: Browser cache (1 hour via Cache-Control header)
- API responses: Network-first strategy with fallback to cache
- Service Worker: Can be added for offline support (future enhancement)

### 5. **SEO & Accessibility**
- Semantic HTML with proper meta tags
- Open Graph social sharing support
- ARIA labels and roles for screen readers
- Keyboard navigation support
- Color contrast compliance
- Loading state indication for accessibility

## Backend Optimizations

### 1. **Response Compression**
Flask-Compress enabled for all responses > 1KB
- Reduces bandwidth usage by 60-75%
- Automatic gzip/brotli compression
- Transparent decompression on client side

### 2. **Caching Strategy**
- Dictionary pre-loaded on startup (101K words)
- In-memory graph store with LRU eviction (max 50 graphs)
- Thread-safe caching for concurrent requests
- Per-skill mutation locks prevent data corruption

### 3. **Thread Pool for Parallel Operations**
- ThreadPoolExecutor for concurrent graph generation
- Parallel ACO optimization for multi-skill learning paths
- 4 worker threads by default (configurable via `.env`)

### 4. **Lazy Module Loading**
- PyTorch/CUDA modules loaded only when needed (difficulty_gnn)
- Graceful fallback to heuristic scoring if torch unavailable
- Reduces startup time and memory footprint

### 5. **Security Headers**
All responses include:
- `X-Content-Type-Options: nosniff` — prevent MIME sniffing
- `X-Frame-Options: SAMEORIGIN` — prevent clickjacking
- `X-XSS-Protection` — legacy XSS filter
- `Strict-Transport-Security` — enforce HTTPS
- `Cache-Control` — appropriate caching directives

### 6. **Error Handling**
- Structured error responses with HTTP status codes
- Logging of all exceptions for debugging
- Graceful degradation (heuristic fallback for unavailable modules)
- Timeout protection for long-running operations

## Database Optimizations

### NeuroMap Data Model
NeuroMap uses in-memory graphs, not traditional databases. Optimizations:
- **Graph Store**: OrderedDict with LRU eviction
- **Index Structures**: O(1) topic lookup by ID
- **Relationship Caching**: Pre-computed prerequisites and dependents
- **Serialization**: JSON-optimized data structures

### Potential Future: Cosmos DB Integration
For scaling to multi-user scenarios with persistent storage:
- Use `userId` + `skillName` as hierarchical partition key
- Embed topic/relation snapshots within skill documents
- Implement graph versioning for audit trails
- See `cosmosdb-best-practices` for guidance

## Production Deployment

### Environment Configuration
Create `.env` file in `src/Backend/`:
```env
FLASK_ENV=production
FLASK_DEBUG=0
SECRET_KEY=<generate-random-key>
HOST=0.0.0.0
PORT=5000
LOG_LEVEL=INFO
ENABLE_COMPRESSION=1
CACHE_TIMEOUT=3600
THREAD_POOL_SIZE=4
MAX_TOPICS_PER_SKILL=50
GRAPH_GENERATION_TIMEOUT=30
```

### Frontend Build for Production
```bash
cd src/Frontend
npm install
npm run build
# Outputs optimized assets to dist/
```

### Backend Deployment
```bash
cd src/Backend
pip install -r requirements.txt
python api.py
# Or with production server (e.g., gunicorn):
gunicorn -w 4 -b 0.0.0.0:5000 api:app
```

### Use Gunicorn for Production
Instead of Flask's development server:
```bash
pip install gunicorn
gunicorn -w 4 -b 0.0.0.0:5000 api:app --timeout=60 --access-logfile -
```
- 4 worker processes (adjust based on CPU cores)
- 60s timeout for long-running graph generation
- Logging to stdout for container platforms

## Monitoring & Profiling

### Frontend Performance
- Use Chrome DevTools > Lighthouse
- Monitor bundle size: `npm run build` shows size
- Analyze React render performance: React DevTools Profiler

### Backend Performance
1. Add timing logs: Already implemented in difficulty scoring
2. Monitor memory usage: Watch graph store LRU eviction
3. Profile expensive operations:
```python
import cProfile
cProfile.run('your_function()')
```

## Optimization Checklist

- [x] Vite code splitting and minification
- [x] Flask response compression
- [x] Security headers on all responses
- [x] SEO meta tags
- [x] Accessibility attributes
- [x] In-memory caching strategy
- [x] Thread-safe mutation locks
- [x] Lazy module loading
- [x] Graceful fallback for missing dependencies
- [x] Environment configuration (.env files)
- [ ] Service Worker for offline support
- [ ] Database persistence (Cosmos DB or similar)
- [ ] Distributed caching (Redis)
- [ ] Rate limiting / throttling
- [ ] Monitoring dashboard (e.g., Datadog)

## Troubleshooting Performance Issues

### Slow Graph Generation
1. Check `MAX_TOPICS_PER_SKILL` in `.env` (increase if needed)
2. Verify thread pool size: `THREAD_POOL_SIZE=4` in `.env`
3. Monitor memory usage during generation
4. Consider enabling GNN difficulty scoring (requires torch)

### High Memory Usage
1. Monitor graph store size: Check LRU eviction logs
2. Adjust `_GRAPH_STORE_MAX = 50` in `api.py` if needed
3. Clear graph store periodically in production

### Frontend Bundle Too Large
1. Run `npm run build` to see size breakdown
2. Check for unused dependencies: `npm ls --depth=2`
3. Verify code splitting in vite.config.ts
4. Use Chrome DevTools > Coverage to find unused code

### API Timeout Issues
1. Increase `GRAPH_GENERATION_TIMEOUT` in `.env`
2. Check backend logs for slow queries
3. Increase thread pool size for concurrent requests
4. Consider upgrading hardware

## Related Documentation
- [Backend API Integration Guide](API_INTEGRATION.md)
- [Frontend Integration Guide](INTEGRATION_GUIDE.md)
- [Detailed Project Summary](../../detailed%20summary.md)
