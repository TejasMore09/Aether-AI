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

export async function brain<T>(
  path: string,
  init: RequestInit & { auth?: boolean } = {},
): Promise<ApiResult<T>> {
  const { auth = true, ...rest } = init
  const headers = new Headers(rest.headers)
  headers.set('Accept', 'application/json')
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
