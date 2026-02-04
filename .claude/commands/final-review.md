# Final Review Workflow for Medical Billing Copilot

A comprehensive PR review workflow for Python/FastAPI code changes.

---

## Step 0: Determine Review Context

Check if this is an initial review or a follow-up:

```bash
git log --oneline -10 | grep -i "Co-Authored-By: Claude"
```

- If Claude commits exist: This is a **follow-up review** - focus on addressing prior feedback
- If no Claude commits: This is an **initial review** - perform full analysis

---

## Step 1: Branch and PR Management

Determine the appropriate branch strategy:

1. Check current branch: `git branch --show-current`
2. Check for uncommitted changes: `git status --porcelain`
3. If on `main` with changes → create feature branch
4. If on feature branch → continue on current branch

---

## Step 2: Launch Three Review Agents in Parallel

Run these three specialized reviewers simultaneously using the Task tool:

### Agent 1: FastAPI & SQLAlchemy Consistency Reviewer

Focus areas for this medical billing codebase:

**Duplicate Logic Detection:**
- Scan for repeated query patterns in database operations
- Identify authentication/authorization checks that could use shared decorators
- Find duplicated Pydantic validation logic across schemas
- Look for repeated error handling patterns that could be centralized

**Existing Pattern Conformance:**
- Verify new endpoints follow the established router pattern in `src/main.py`
- Check that new models follow conventions in `src/db/models.py`
- Ensure schemas match existing patterns in `src/schemas/`
- Validate configuration follows `src/config.py` patterns

**Codebase Integration:**
- Flag any utilities that duplicate existing functionality
- Identify opportunities to extend existing base classes
- Check for query patterns that could use existing session management

---

### Agent 2: Python Clean Code & Type Safety Reviewer

Focus areas:

**Type Annotation Completeness:**
- All function parameters have type hints
- Return types are specified (not implicit `None`)
- Pydantic models use proper field types
- Generic types use proper parameterization (`list[str]` not `list`)

**Async/Await Correctness:**
- Async functions are properly awaited
- No blocking calls inside async functions (use `run_in_executor` if needed)
- Database sessions use async patterns correctly
- No mixing of sync and async inappropriately

**Single Responsibility Violations:**
- Endpoint functions doing too much (should delegate to services)
- Models with business logic (should be in separate service layer)
- Schemas with transformation logic beyond validation

**Code Complexity:**
- Deeply nested conditionals (flatten with early returns)
- Functions exceeding 20 lines (candidates for decomposition)
- Complex list comprehensions (extract to named functions)

---

### Agent 3: Security & Healthcare Compliance Auditor

Focus areas critical for medical billing:

**Authentication & Authorization:**
- JWT token handling follows security best practices
- Password hashing uses bcrypt with adequate rounds
- Failed login tracking prevents brute force attacks
- User role checks on sensitive endpoints

**Data Protection (HIPAA Considerations):**
- No PII/PHI in log statements
- Query logs don't expose sensitive patient data
- Error messages don't leak internal system details
- Session management properly isolates user data

**Input Validation & Injection Prevention:**
- All user inputs validated via Pydantic before use
- SQLAlchemy ORM used (no raw SQL string concatenation)
- Path parameters validated and typed
- Query parameters bounds-checked where applicable

**Defensive Code Anti-Patterns to Flag:**
- Overly broad exception handlers (`except Exception: pass`)
- Silent failures that hide broken assumptions
- Unnecessary `Optional` types that complicate logic
- Default values that mask missing required data

---

## Step 3: Reconcile Agent Recommendations

When agents provide conflicting guidance:

1. **Prioritize existing patterns** - Consistency with codebase trumps theoretical best practices
2. **Security concerns override convenience** - Never skip security recommendations
3. **Healthcare compliance is non-negotiable** - HIPAA-related suggestions must be addressed
4. **Track skipped suggestions** - Document why any recommendation was not implemented

Create a reconciliation summary:
```
ACCEPTED:
- [List changes implemented from each agent]

SKIPPED (with justification):
- [List suggestions not implemented and why]
```

---

## Step 4: Run Comprehensive Test Suite

Execute all validation checks:

### 4.1 Linting (Ruff)
```bash
ruff check src/ tests/
```

### 4.2 Type Checking (if mypy configured)
```bash
mypy src/ --ignore-missing-imports || echo "mypy not configured"
```

### 4.3 Unit Tests with Coverage
```bash
pytest tests/ -v --tb=short --cov=src --cov-report=term-missing
```

### 4.4 Async Test Verification
```bash
pytest tests/ -v -k "async" || echo "No async-specific tests"
```

### 4.5 Database Migration Check
```bash
alembic check || echo "No pending migrations"
```

### 4.6 Application Startup Verification
```bash
timeout 10 uvicorn src.main:app --host 127.0.0.1 --port 8099 &
sleep 3
curl -f http://127.0.0.1:8099/health || echo "Health check failed"
pkill -f "uvicorn src.main:app.*8099" || true
```

---

## Step 5: Commit and Push Changes

If all checks pass:

1. Stage changes: `git add -A`
2. Create descriptive commit with co-author attribution
3. Push to remote: `git push -u origin <branch>`

---

## Step 6: Generate Review Summary

Provide a structured summary:

```markdown
## Final Review Summary

### Changes Made
- [List of modifications]

### Tests Executed
| Check | Status |
|-------|--------|
| Ruff Linting | PASS/FAIL |
| Unit Tests | PASS/FAIL (X/Y passed) |
| Coverage | X% |
| App Startup | PASS/FAIL |
| Migrations | PASS/FAIL |

### Agent Recommendations
**Implemented:**
- [From Consistency Reviewer]: ...
- [From Clean Code Reviewer]: ...
- [From Security Auditor]: ...

**Deferred (with justification):**
- ...

### Follow-up Recommended
- [ ] Yes - Another review pass needed
- [ ] No - Ready for human review
```

---

## Common Code Smells in FastAPI/SQLAlchemy Stack

Watch for these patterns specific to this codebase:

1. **N+1 Query Problems** - Loops that trigger individual DB queries instead of batch loading
2. **Missing Dependency Injection** - Hardcoded dependencies instead of using FastAPI's `Depends()`
3. **Sync in Async** - Blocking operations in async endpoints
4. **Unvalidated External Data** - Trusting data without Pydantic validation
5. **Leaky Abstractions** - SQLAlchemy models exposed directly in API responses
6. **Missing Index Hints** - Queries on unindexed columns (check migrations)
7. **Stale Session State** - Not refreshing SQLAlchemy objects after commits
8. **Overly Permissive CORS** - Security misconfigurations in FastAPI middleware
9. **Hardcoded Secrets** - API keys or passwords not using environment variables
10. **Missing Audit Trail** - Healthcare operations without proper logging to `query_logs`
