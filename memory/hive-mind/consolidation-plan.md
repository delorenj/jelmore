# Code Consolidation Plan - Jelmore Architecture Migration

## Analysis Summary

### Current Dual Architecture Problem
The project currently has TWO competing implementations:
- `/app/` - Full implementation with database models, API endpoints, core services
- `/src/jelmore/` - Skeleton implementation with placeholder TODOs

### Key Findings

#### /app Implementation (Source of Truth)
**Strengths:**
- Complete FastAPI application with proper lifespan management
- Comprehensive session management (ClaudeCodeSession, SessionManager)
- Database integration with SQLAlchemy async models
- Redis client for caching/session storage
- NATS event publishing for distributed architecture
- WebSocket streaming for real-time output
- Structured logging with structlog
- Well-organized API routes with proper error handling

**Key Components:**
- `main.py` - Full FastAPI app with database/redis/nats initialization
- `models/session.py` - SessionStatus enum, Session SQLAlchemy model
- `api/sessions.py` - Complete REST API + WebSocket endpoints
- `core/claude_code.py` - Claude Code subprocess wrapper (218 lines)
- `core/database.py` - Async SQLAlchemy setup
- `core/redis_client.py` - Redis connection management
- `core/nats_client.py` - NATS event publishing
- `config.py` - Comprehensive settings with database_url property

#### /src/jelmore Implementation (Skeleton)
**Strengths:**
- Clean directory structure (api/, models/, services/, utils/)
- Modern configuration with lru_cache and better typing
- Loguru logging (lighter than structlog)

**Weaknesses:**
- main.py has TODOs instead of implementation
- Empty directories (no actual implementation files)
- Missing all core functionality

## Migration Strategy

### Phase 1: Configuration Consolidation ✅
**Goal:** Merge best practices from both config files
**Actions:**
- Use src/jelmore/config.py as base (better typing, lru_cache)
- Add missing settings from app/config.py
- Ensure backward compatibility

### Phase 2: Core Services Migration
**Goal:** Move all /app/core functionality to /src/jelmore/services
**Actions:**
- `app/core/database.py` → `src/jelmore/services/database.py`
- `app/core/redis_client.py` → `src/jelmore/services/redis.py`
- `app/core/nats_client.py` → `src/jelmore/services/nats.py`
- `app/core/claude_code.py` → `src/jelmore/services/claude_code.py`

### Phase 3: Models Migration
**Goal:** Move database models to proper location
**Actions:**
- `app/models/session.py` → `src/jelmore/models/session.py`
- Add `__init__.py` with proper exports

### Phase 4: API Migration
**Goal:** Move API endpoints to proper location
**Actions:**
- `app/api/sessions.py` → `src/jelmore/api/sessions.py`
- Update imports to use new service locations

### Phase 5: Main Application Update
**Goal:** Replace skeleton main.py with full implementation
**Actions:**
- Merge functionality from app/main.py into src/jelmore/main.py
- Update all imports to use new consolidated structure
- Ensure proper initialization order

### Phase 6: Docker & Deployment
**Goal:** Update deployment configuration
**Actions:**
- Dockerfile already points to src/jelmore - ✅ Good!
- Verify all import paths work correctly

### Phase 7: Cleanup
**Goal:** Remove duplicate code
**Actions:**
- Verify consolidated implementation works
- Remove /app directory entirely

## Import Path Changes

### Before (app-based)
```python
from app.config import settings
from app.core.database import init_db, close_db
from app.core.redis_client import init_redis, close_redis
from app.core.nats_client import init_nats, close_nats
from app.api import router
```

### After (jelmore-based)
```python
from jelmore.config import get_settings
from jelmore.services.database import init_db, close_db
from jelmore.services.redis import init_redis, close_redis
from jelmore.services.nats import init_nats, close_nats
from jelmore.api import router
```

## Risk Mitigation

### Backward Compatibility
- Keep same API endpoints and behavior
- Maintain same configuration environment variables
- Preserve same database schema

### Testing Strategy
- Test health endpoint immediately after consolidation
- Verify all API endpoints work with Postman/curl
- Test WebSocket streaming functionality
- Validate database connectivity
- Check Redis and NATS connections

### Rollback Plan
- Keep /app directory until full verification
- Docker already uses src/jelmore so less risk
- Can quickly revert imports if needed

## Success Criteria

1. ✅ Single source of truth under `/src/jelmore`
2. ✅ All functionality preserved from /app implementation
3. ✅ Docker build and run successfully
4. ✅ Health endpoint responds correctly
5. ✅ Session API endpoints work (CRUD operations)
6. ✅ WebSocket streaming functional
7. ✅ Database migrations work
8. ✅ No duplicate code remaining

## Implementation Order

1. **Configuration merge** (low risk, foundational)
2. **Services migration** (medium risk, core functionality)
3. **Models migration** (low risk, simple move)
4. **API migration** (medium risk, endpoint behavior)
5. **Main application** (high risk, integration point)
6. **Testing & validation** (critical, verification)
7. **Cleanup** (low risk, final step)

---

*This plan ensures a systematic, low-risk migration while preserving all functionality and maintaining the superior architecture of the /app implementation.*