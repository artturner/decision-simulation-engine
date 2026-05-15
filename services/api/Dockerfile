FROM python:3.12-slim

WORKDIR /app

# System dependency: curl is used by the healthcheck probe
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# ── Internal packages (engine + expr) ────────────────────────────────────────
# These are local Python packages that live in the monorepo's packages/
# directory.  The build context must be the repo root so these paths resolve.
COPY packages/expr   /tmp/pkg/expr
COPY packages/engine /tmp/pkg/engine
RUN pip install --no-cache-dir /tmp/pkg/expr /tmp/pkg/engine

# ── API dependencies ──────────────────────────────────────────────────────────
COPY services/api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Application code ──────────────────────────────────────────────────────────
COPY services/api/ .

# Create media directory (bind-mounted in production)
RUN mkdir -p media

EXPOSE 8000

# docker-compose overrides this command to prepend "alembic upgrade head &&"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
