# Deploying Aether

One file stands the whole platform up:

```bash
cd deploy
cp .env.example .env      # fill it in — nothing has a working default
docker compose up -d --build
```

Ten containers: Postgres with pgvector, Redis, Temporal, the three APIs, the
monitor worker, both front ends, and Caddy in front holding the certificates.

**`--build` is not optional the first time, and forgetting it is the first
mistake this made.** Compose reuses an image that already exists under the
tag, so `up -d` after a code change silently runs the old one. That is how the
first run of this stack came up with a migration missing and the application
role locked out of its own database — every service healthy-looking, the
readiness probe correctly reporting `password authentication failed`.

---

## What "free tier" actually means here

The plan said "free tier", so this is the honest answer rather than the
convenient one.

Measured, with the full stack idle on a laptop:

| | |
|---|---|
| Memory, all ten containers | **~690 MiB** resident |
| Disk, images | **~2.6 GB** |
| Disk, volumes at rest | ~280 MB and growing with the database |

The platform image alone is 1.1 GB, and that is mostly not our code: litellm
is 115 MB and drags in botocore and the OpenAI SDK for a product that calls
one provider, onnxruntime is 66 MB, temporalio 57 MB, numpy 71 MB. The
embedding model adds 65 MB and is deliberately baked in rather than downloaded
on first use.

**No PaaS free tier will run this.** Render, Railway and Fly are all built
around one or two small always-on processes with a managed database; ten
containers with Temporal and a persistent volume is not what those free plans
are. Anyone who tells you otherwise is quoting the plan and not the workload.

What genuinely fits:

- **Oracle Cloud Always Free** — 4 ARM cores and 24 GB of RAM, free with no
  expiry, and the only thing on this list that costs nothing and is not a
  trial. It is what this is written for. Two caveats worth knowing before you
  spend an afternoon: the images here have only been built and run on x86, and
  ARM needs `docker buildx build --platform linux/arm64` (the base images and
  every wheel involved have ARM builds, so this should be a rebuild rather
  than a port — but "should be" is not "has been"); and Oracle's free capacity
  in a given region is frequently exhausted, which is not documented anywhere
  you will find before signing up.
- **Any small VPS** — 2 vCPU and 4 GB is comfortable, at roughly $10–20 a
  month. Hetzner, DigitalOcean, Vultr.

What does not fit: anything with less than 2 GB of RAM, and anything without a
persistent disk.

**Temporal is the heaviest thing here** and the only one whose value is not
yet fully drawn. It runs the autonomous monitor loop, at 154 MiB plus its two
databases inside Postgres. If a deployment has to be made smaller, that is
where to look first — and it is a real architectural decision, not a config
change, so it is not made here.

---

## Before the first start

**DNS first.** `APP_DOMAIN` must already resolve to the machine. Caddy asks
Let's Encrypt for a certificate the moment it starts, and repeated failures are
rate-limited — five per hostname per week, after which the site is simply down
until the window rolls.

**Two database passwords, not one.** The owner role creates and alters schema;
the application role cannot. Row-level security is only enforced against a
non-owner, so this separation is not tidiness — it is what makes tenant
isolation real. A SQL injection in the product cannot drop a table because the
role holding the connection has never been able to.

**Two signing secrets, and they must differ.** One signs customer sessions and
one signs staff sessions. Sharing them would make a leaked customer token a
fleet-wide staff credential.

The services check all of this at startup and **refuse to run** rather than
starting on a development configuration (D60). Every problem is reported at
once, so fixing a deployment is one pass rather than one restart per mistake:

```
aether.core.config.Misconfigured: refusing to start with this configuration:
  - AETHER_JWT_SECRET is still the value shipped in the repository
  - AETHER_STAFF_JWT_SECRET is still the value shipped in the repository
  - AETHER_DATABASE_URL still carries the development password
  - AETHER_WEB_BASE_URL must be https in production
```

---

## What is exposed, and what is not

Only the proxy binds a public port. The database, Redis, Temporal, all three
APIs and both Next.js servers are reachable on the compose network and nowhere
else.

That is load-bearing in two ways.

The front ends are backends-for-frontends: the browser never holds a platform
token, because there is no route by which it could reach an API to use one.

And the throttle now trusts a header. `AETHER_CLIENT_IP_SOURCE=forwarded` is
correct here because Caddy replaces any `X-Forwarded-For` a caller sends, and
each front end passes the resulting address on to the API. **Publishing a route
to any API would break that** — anything able to reach the control plane
directly could name itself whatever it liked, and per-address throttling would
become theatre without changing a line of code.

The staff console is served on `CONSOLE_DOMAIN`, which defaults to a
`.localhost` name that resolves nowhere. Reaching it should mean a VPN, an SSH
tunnel, or an address allowlist. It is the fleet-wide surface; publishing it on
the open internet because that was the easier default is how a staff login page
becomes the softest target on the platform.

---

## After it is up

```bash
docker compose ps                       # every API should say (healthy)
docker compose logs -f control-plane
docker compose exec db psql -U aether -d aether
```

The health probes ask `/readyz`, which touches the database, rather than
`/healthz`, which only proves the process is alive and would report a green
month through a total outage (D59). Point an external uptime monitor at
`https://$APP_DOMAIN` — the internal checks restart a broken container and
cannot tell you the machine is gone.

**Create the first staff account**, which nothing does automatically:

```bash
docker compose exec main-brain python -c "
from aether.core.models import StaffRole
from aether.core.staff import create_admin
create_admin('you@example.com', 'a-long-password-you-chose', StaffRole.admin)"
```

---

## Upgrading

```bash
git pull
docker compose up -d --build
```

The `migrate` container runs first and the services wait on it finishing —
that is what `service_completed_successfully` in the compose file buys, and
without it four services would race to run migrations at once.

Set `AETHER_VERSION` to a git sha rather than leaving it at `latest` for
anything you would want to roll back. `latest` is why nobody can say what is
deployed.

---

## What this does not do

Said plainly, because a deployment guide that reads as complete when it is not
is worse than no guide.

- **It has never run on a real host.** Everything here is verified on one
  machine: the stack comes up, serves HTTPS, the rate limit fires, the
  forwarded address reaches the throttle. None of that is the same as a month
  of uptime on the internet.
- **No backups.** That is 6.2, and it is the next thing.
- **One machine, no failover.** A compose file is the right size for one
  machine and the wrong tool for two. When there is a second, this decision is
  worth reopening rather than extending.
- **No log aggregation.** Logs live in the containers. `docker compose logs` is
  the whole story, and it ends when a container is recreated.
- **No CI.** Images are built on the host being deployed to, which means the
  build is only as reproducible as that host. The lockfiles are now generated
  in Linux for exactly this reason — they were previously generated on Windows
  and `npm ci` refused them.
