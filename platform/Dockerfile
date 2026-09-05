# One image, four entrypoints.
#
# The control plane, the agent runtime, the main brain and the Temporal worker
# are the same Python package with different commands. Four images would be
# four things to keep in step for no benefit — the code is identical, and the
# isolation that matters is at the port and the database role, not at the
# image. Which one a container becomes is decided by its command.
#
# Multi-stage, so no compiler survives into what runs. Non-root, because a
# container that can write its own code is one bug away from persisting an
# attacker.
#
# **Build from the repository root**, not from platform/:
#
#     docker build -f platform/Dockerfile -t aether/platform .
#
# because `reference/` sits beside `platform/` and the image needs it. That is
# not an arbitrary layout choice — the reference tables are shared with the
# extraction tooling in that directory and are versioned with the repository
# rather than with the service.

# ── Build ─────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /build

# Its own virtualenv rather than the system site-packages, so the final stage
# copies one directory and inherits nothing else from this one.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Dependencies before source, so their layer is reused across every code
# change. That is the difference between a ten-second rebuild and a
# three-minute one, and it is the reason the package __init__ is copied alone.
COPY platform/pyproject.toml platform/README.md ./
COPY platform/src/aether/__init__.py src/aether/__init__.py
RUN pip install .

COPY platform/src/ src/
RUN pip install --no-deps .

# The embedding model, baked in.
#
# fastembed downloads it lazily on first use. In a container that means the
# first request touching the knowledge base stalls for a ~50MB download, and
# fails outright wherever egress is restricted — turning a network policy into
# a silently degraded agent memory. Better to pay for it here, once, in a
# layer that caches.
ARG EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
ENV FASTEMBED_CACHE_PATH=/opt/models
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('${EMBEDDING_MODEL}')"

# ── Run ───────────────────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# curl for the container healthcheck, which asks /readyz rather than assuming
# that a listening socket means a working service (D59).
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 10001 aether

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    FASTEMBED_CACHE_PATH=/opt/models \
    AETHER_REFERENCE_DIR=/app/reference

COPY --from=builder /opt/venv /opt/venv
# Owned by the runtime user: fastembed writes a small tree cache beside the
# model, and a read-only directory turns that into a permission warning on
# every single start plus repeated work it cannot memoise.
COPY --from=builder --chown=aether:aether /opt/models /opt/models

WORKDIR /app

# Migrations are not part of the installed package. They are needed by the
# one-shot migrate container, which runs as the schema owner rather than as
# the application role.
COPY platform/alembic.ini ./
COPY platform/migrations/ migrations/

# The committed reference tables. `domains/reference.py` used to find these by
# walking up from its own file to the repository root — a path that does not
# exist once the package is installed, so every sector would have silently
# lost its bands in here. AETHER_REFERENCE_DIR above is the fix.
COPY reference/ reference/

USER aether

EXPOSE 8100 8200 8300

# Overridden per service in the compose file. The default is the control
# plane, because a container started with no command should be the thing a
# customer talks to rather than a surprise.
CMD ["uvicorn", "aether.control_plane.app:app", "--host", "0.0.0.0", "--port", "8100"]
