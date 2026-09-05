import { headers } from 'next/headers'

import 'server-only'

import { readSession } from './session'

/**
 * Server-side client for the main brain, and nothing else.
 *
 * There is exactly one base URL here because there is exactly one service
 * this application is allowed to talk to. If a future page needs tenant data,
 * it goes through the brain's gated endpoints and inherits the break-glass
 * check — it does not get a second client pointed at the agent runtime.
 */

const MAIN_BRAIN = process.env.AETHER_MAIN_BRAIN_URL ?? 'http://localhost:8300'

export type ApiOk<T> = { ok: true; data: T }
export type ApiErr = { ok: false; status: number; message: string }
export type ApiResult<T> = ApiOk<T> | ApiErr

function friendly(status: number, detail: unknown): string {
  if (status === 401) return 'Your staff session expired. Sign in again.'
  if (status === 403 && typeof detail === 'string') return detail
  if (status === 403) return 'Your staff role does not allow that.'
  if (status === 404) return 'Not found.'
  if (typeof detail === 'string' && detail.length > 0 && detail.length < 400) return detail
  if (status >= 500) return 'The main brain returned an error.'
  return 'That request could not be completed.'
}

/**
 * The customer's address, carried one hop further.
 *
 * This is a backend-for-frontend: the browser never talks to the platform
 * API, so from the API's point of view every request on the platform comes
 * from this one Next.js server. That is why 6.4's per-address throttling was
 * built and then switched off — counting against that address would collapse
 * every customer into a single bucket, where twenty bad guesses by anyone
 * locks out everyone.
 *
 * Caddy knows who the caller is and writes it into X-Forwarded-For, replacing
 * anything the caller tried to put there. Passing it on is what makes
 * AETHER_CLIENT_IP_SOURCE=forwarded true rather than a guess; without this
 * function that setting reads a header nobody set.
 *
 * **This is only safe because the API is unreachable from outside the compose
 * network.** The API trusts whatever arrives in this header, so anything able
 * to reach it directly could forge an address. Publishing a route to the
 * control plane would quietly turn per-address throttling back into theatre.
 *
 * Returns null outside a request scope — a background job, a build-time
 * render — where there is no caller to name and inventing one would be worse
 * than saying nothing.
 */
async function forwardedFor(): Promise<string | null> {
  try {
    const incoming = await headers()
    // Leftmost: Caddy puts the real client first and the API reads it the
    // same way. Anything after it is a proxy hop, and there are none here.
    const forwarded = incoming.get('x-forwarded-for')
    if (forwarded) return forwarded.split(',')[0].trim()
    return incoming.get('x-real-ip')
  } catch {
    return null
  }
}

export async function brain<T>(
  path: string,
  init: RequestInit & { auth?: boolean } = {},
): Promise<ApiResult<T>> {
  const { auth = true, ...rest } = init
  const headers = new Headers(rest.headers)
  headers.set('Accept', 'application/json')

  // See forwardedFor(): the API's caller is this server, so the
  // customer's own address has to be carried explicitly or 6.4's
  // per-address throttle has nothing true to count.
  const caller = await forwardedFor()
  if (caller) headers.set('X-Forwarded-For', caller)
  if (rest.body && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  if (auth) {
    const session = await readSession()
    if (!session) return { ok: false, status: 401, message: friendly(401, null) }
    headers.set('Authorization', `Bearer ${session.token}`)
  }

  let response: Response
  try {
    response = await fetch(`${MAIN_BRAIN}${path}`, {
      ...rest,
      headers,
      cache: 'no-store', // fleet state is never cached; a stale incident view is worse than a slow one
      signal: AbortSignal.timeout(15_000),
    })
  } catch {
    return {
      ok: false,
      status: 0,
      message: 'Cannot reach the main brain. Is it running on port 8300?',
    }
  }

  let payload: unknown = null
  try {
    payload = await response.json()
  } catch {
    payload = null
  }

  if (!response.ok) {
    const detail =
      payload && typeof payload === 'object' && 'detail' in payload
        ? (payload as { detail: unknown }).detail
        : null
    return {
      ok: false,
      status: response.status,
      message: friendly(response.status, typeof detail === 'string' ? detail : null),
    }
  }

  return { ok: true, data: payload as T }
}

// ── Shapes (mirror the main brain's responses) ───────────────────────────────

export type FleetRow = {
  tenant_id: string
  name: string
  slug: string
  is_active: boolean
  created_at: string
  active_agents: number
  observation_count: number
  quarantined_count: number
  last_observation_at: string | null
  pending_approvals: number
  configured_domains: number
  active_keys: number
  month_spend_usd: number
  failed_notifications: number
  knowledge_chunks: number
  last_knowledge_at: string | null
  unindexed_decisions: number
}

export type Grant = {
  id: string
  admin_email: string
  tenant_id: string
  tenant_name: string
  tenant_slug: string
  reason: string
  scope: 'read_only' | 'operate'
  granted_at: string
  expires_at: string
  ended_at: string | null
  ended_by: string
  live: boolean
}

export type Fault = {
  fingerprint: string
  service: string
  exception_type: string
  location: string
  occurrences: number
  tenants_seen: number
  first_seen_at: string
  last_seen_at: string
  alerted: boolean
  resolved_at: string | null
  resolved_by: string
  reference: string
  // Present only for engineers and admins. An observer's payload omits both
  // fields entirely rather than blanking them, so the type says optional and
  // the page has to handle their absence (D57).
  message?: string
  traceback?: string
}

export type OpsHealth = {
  service: string
  environment: string
  uptime_seconds: number
  database: { ok: boolean; detail: string }
  mail_configured: boolean
  alerts_configured: boolean
  healthy: boolean
  errors: { open?: number; active_last_hour?: number; occurrences_last_day?: number; unavailable?: string }
}

export type TrailEntry = {
  id: string
  created_at: string
  admin_email: string
  action: string
  tenant_id: string | null
  grant_id: string | null
  details: Record<string, unknown>
}

export type TenantObservation = {
  id: string
  observed_at: string
  domain: string
  source: string
  status: 'accepted' | 'quarantined'
  metrics: Record<string, number>
  issues: unknown
  performance: number
  drift_fraction: number
}

export type TenantAuditEntry = {
  id: string
  created_at: string
  domain: string
  action: string
  triggered_by: string
  risk_level: string
  status: string
  details: Record<string, unknown>
}
