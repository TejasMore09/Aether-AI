# Caddy with rate limiting compiled in.
#
# Rate limiting is not part of core Caddy, so the binary has to be built with
# the plugin. That is the price of the trade, and the trade is worth naming:
# nginx has `limit_req` built in and needs certbot, a renewal timer and a
# reload hook for HTTPS; Caddy gets certificates and renews them by itself and
# needs this build step for rate limiting. Automatic certificates are the
# harder thing to get right and the worse thing to get wrong — an expired
# certificate is an outage, and a missed rate limit is a bad afternoon.
#
# Versions are pinned. An edge that silently upgrades itself is an edge whose
# behaviour nobody can reproduce.

FROM caddy:2.10-builder AS builder

RUN xcaddy build \
    --with github.com/mholt/caddy-ratelimit@v0.1.0

FROM caddy:2.10

COPY --from=builder /usr/bin/caddy /usr/bin/caddy
