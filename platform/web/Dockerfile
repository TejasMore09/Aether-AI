# The customer dashboard.
#
# Build from the repository root, like the platform image:
#
#     docker build -f platform/web/Dockerfile -t aether/web .
#
# **Nothing here talks to the main brain**, and that is a deployment property
# rather than a convention. This image carries no staff configuration, so a
# routing mistake in the customer app cannot become a cross-boundary mistake:
# there is no credential in the container to misuse.

FROM node:24-slim AS deps
WORKDIR /app
# Lockfile only, so this layer survives every source change. `npm ci` rather
# than `npm install`: a deploy must build the dependency tree that was tested,
# not the newest one that resolves today.
COPY platform/web/package.json platform/web/package-lock.json ./
RUN npm ci

FROM node:24-slim AS builder
WORKDIR /app
COPY --from=deps /app/node_modules node_modules
COPY platform/web/ ./
# Next bakes NODE_ENV=production itself; this is for anything reading it
# during the build.
ENV NODE_ENV=production
RUN npm run build

FROM node:24-slim AS runtime
WORKDIR /app

ENV NODE_ENV=production \
    PORT=3000 \
    HOSTNAME=0.0.0.0 \
    NEXT_TELEMETRY_DISABLED=1

RUN useradd --create-home --uid 10002 nextjs

# The standalone bundle is the server plus only the modules it imports —
# roughly a tenth of node_modules, and none of the source.
COPY --from=builder --chown=nextjs:nextjs /app/.next/standalone ./
COPY --from=builder --chown=nextjs:nextjs /app/.next/static ./.next/static
# No `public/` to copy: this application ships no static assets, every icon
# being inline SVG. A COPY for a directory that does not exist fails the build
# rather than being harmlessly skipped, so it is left out until there is
# something to put in it.

USER nextjs
EXPOSE 3000

CMD ["node", "server.js"]
