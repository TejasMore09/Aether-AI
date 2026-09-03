import 'server-only'

import { readSession } from './session'

/**
 * Server-side client for the two platform services.
 *
 * Runs only on the server: the browser never learns these hostnames and never
 * holds a token. Failures are returned as typed results rather than thrown, so
 * pages can render a real error state instead of a crash, and API error text is
 * never passed through verbatim to the UI.
 */

const CONTROL_PLANE = process.env.AETHER_CONTROL_PLANE_URL ?? 'http://localhost:8100'
const AGENT_RUNTIME = process.env.AETHER_AGENT_RUNTIME_URL ?? 'http://localhost:8200'

export type ApiOk<T> = { ok: true; data: T }
export type ApiErr = { ok: false; status: number; message: string }
export type ApiResult<T> = ApiOk<T> | ApiErr

type Service = 'control' | 'runtime'

function baseFor(service: Service): string {
  return service === 'control' ? CONTROL_PLANE : AGENT_RUNTIME
}

function friendly(status: number, detail: unknown): string {
  if (status === 401) return 'Your session expired. Please sign in again.'
  if (status === 403) return 'Your role does not allow this action.'
  if (status === 404) return 'Not found.'
  if (status === 503) return 'That service is temporarily unavailable. Try again shortly.'
  if (typeof detail === 'string' && detail.length > 0 && detail.length < 300) return detail
  if (status >= 500) return 'The platform returned an error. Please try again.'
  return 'That request could not be completed.'
}

async function request<T>(
  service: Service,
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
    response = await fetch(`${baseFor(service)}${path}`, {
      ...rest,
      headers,
      cache: 'no-store', // operational data is never cached
      signal: AbortSignal.timeout(15_000),
    })
  } catch {
    return {
      ok: false,
      status: 0,
      message: 'Cannot reach the platform services. Are they running?',
    }
  }

  if (response.status === 204) return { ok: true, data: undefined as T }

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

export const api = {
  control: <T>(path: string, init?: RequestInit & { auth?: boolean }) =>
    request<T>('control', path, init),
  runtime: <T>(path: string, init?: RequestInit & { auth?: boolean }) =>
    request<T>('runtime', path, init),
}

// ── Response shapes (mirror the FastAPI models) ──────────────────────────────

export type TenantInfo = {
  id: string
  name: string
  slug: string
  currency: string
  sector: string
  sector_label: string
}

export type BandChange = {
  domain: string
  domain_label: string
  metric: string
  metric_label: string
  unit: string
  pack_good: number
  sector_good: number
  stricter: boolean
  basis: string
}

export type SectorOption = {
  key: string
  label: string
  summary: string
  has_bands: boolean
  bands_note?: string
  changes: BandChange[]
  source_note: string
  changes_nothing: boolean
}

export type AgentInfo = {
  id: string
  name: string
  kind: 'nano' | 'mega'
  is_active: boolean
}

export type Approval = {
  id: string
  created_at: string
  domain: string
  action: string
  reason: string
  risk_level: 'LOW' | 'MEDIUM' | 'HIGH'
  expected_loss: number
  currency: string
  diagnosis: string | null
  diagnosis_source: 'llm' | 'fallback' | null
}

export type AuditEntry = {
  id: string
  created_at: string
  domain: string
  action: string
  triggered_by: string
  risk_level: string
  status: string
  details: Record<string, unknown>
}

export type QualityIssue = {
  metric: string | null
  code: string
  severity: 'error' | 'warning'
  message: string
}

export type ObservationRow = {
  id: string
  observed_at: string
  drift_fraction: number
  performance: number
  source: string
  status: 'accepted' | 'quarantined'
  metrics: Record<string, number>
  issues: QualityIssue[]
}

export type MetricSpec = {
  key: string
  label: string
  unit: string
  required: boolean
  direction: 'lower_better' | 'higher_better' | 'neutral'
  healthy_range: [number | null, number | null]
  description: string
}

export type DomainPack = {
  key: string
  label: string
  version: number
  summary: string
  reporting_window_hours: number
  metrics: MetricSpec[]
  actions: { slot: string; label: string; description: string }[]
}

export type UsageReport = {
  month_spend_usd: number
  monthly_budget_usd: number
  budget_remaining_usd: number
  by_purpose: Record<string, { calls: number; cost_usd: number; tokens: number }>
}

export type ApiKeyRow = {
  id: string
  name: string
  prefix: string
  created_at: string
  created_by: string
  last_used_at: string | null
  revoked: boolean
}

export type CrossDomainFinding = {
  relation_id: string
  label: string
  confidence: 'mechanical' | 'strong'
  domains: string[]
  mechanism: string
  guidance: string
  lag_note: string
  readings: Record<string, number>
  daily_amount: number
  currency: string
  exposure_basis: string
  per_domain: { domain: string; daily_amount: number; basis: string }[]
  severity: number
  corroborated: boolean
  corroborated_by: string[]
  subsumes: string[]
  inherited_risk_level: string
  requires_approval: boolean
  also_seen: string[]
  also_covers: string[]
}

export type BusinessView = {
  captured_at: string
  findings: CrossDomainFinding[]
  impaired: string[]
  silent: string[]
  domains: Record<string, unknown>
}

export type NotificationRow = {
  id: string
  created_at: string
  kind: string
  channel: string
  recipient: string
  subject: string
  status: string
  ref_id: string | null
}
