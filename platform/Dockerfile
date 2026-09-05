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
#
# postgresql-client **16**, matching the server, from PostgreSQL's own
# repository because Debian does not ship 16 in every release.
#
# The version match is not incidental. A newer pg_restore against an older
# server emits `SET transaction_timeout`, which the server does not recognise
# — and then exits 0 anyway. That was measured during 6.2 with a 18 client
# against this 16 server. The restore survives it, but a backup tool whose
# ordinary output contains errors is a tool whose output nobody reads.
#
# The codename is read from the base image rather than written down. Hardcoding
# `bookworm` is how the first version of this line failed: python:3.12-slim had
# moved to trixie underneath it.
ARG PG_MAJOR=16
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates gnupg \
    && install -d /usr/share/postgresql-common/pgdg \
    && curl -fsS https://www.postgresql.org/media/keys/ACCC4CF8.asc \
       -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
    && . /etc/os-release \
    && echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt ${VERSION_CODENAME}-pgdg main" \
       > /etc/apt/sources.list.d/pgdg.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends "postgresql-client-${PG_MAJOR}" \
    && apt-get purge -y gnupg \
    && apt-get autoremove -y \
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

# Where dumps land. Created and owned here so that a volume mounted over it
# inherits the ownership, rather than arriving root-owned and unwritable —
# which is the ordinary way a backup container fails on its first night and
# not before.
RUN install -d -o aether -g aether /var/lib/aether/backups

USER aether

EXPOSE 8100 8200 8300

# Overridden per service in the compose file. The default is the control
# plane, because a container started with no command should be the thing a
# customer talks to rather than a surprise.
CMD ["uvicorn", "aether.control_plane.app:app", "--host", "0.0.0.0", "--port", "8100"]
