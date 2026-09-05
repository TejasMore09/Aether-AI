# The staff console.
#
# Build from the repository root, like the platform image:
#
#     docker build -f platform/console/Dockerfile -t aether/console .
#
# A separate image from web/ for the same reason it is a separate application:
# this one holds main-brain configuration and the customer dashboard must not.
# It is also the one that should not be publicly reachable — the compose file
# binds it to localhost, and a real deployment puts it behind a VPN or an
# address allowlist. Being a different container is what makes that possible
# to express at all.

FROM node:24-slim AS deps
WORKDIR /app
# Lockfile only, so this layer survives every source change. `npm ci` rather
# than `npm install`: a deploy must build the dependency tree that was tested,
# not the newest one that resolves today.
COPY platform/console/package.json platform/console/package-lock.json ./
RUN npm ci

FROM node:24-slim AS builder
WORKDIR /app
COPY --from=deps /app/node_modules node_modules
COPY platform/console/ ./
# Next bakes NODE_ENV=production itself; this is for anything reading it
# during the build.
ENV NODE_ENV=production
RUN npm run build

FROM node:24-slim AS runtime
WORKDIR /app

ENV NODE_ENV=production \
    PORT=3100 \
    HOSTNAME=0.0.0.0 \
    NEXT_TELEMETRY_DISABLED=1

RUN useradd --create-home --uid 10003 nextjs

# The standalone bundle is the server plus only the modules it imports —
# roughly a tenth of node_modules, and none of the source.
COPY --from=builder --chown=nextjs:nextjs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nextjs /app/.next/static ./.next/static
# No `public/` to copy: this application ships no static assets, every icon
# being inline SVG. A COPY for a directory that does not exist fails the build
# rather than being harmlessly skipped, so it is left out until there is
# something to put in it.

USER nextjs
EXPOSE 3100

CMD ["node", "server.js"]
