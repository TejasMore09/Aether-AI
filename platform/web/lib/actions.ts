'use server'

import { redirect } from 'next/navigation'
import { revalidatePath } from 'next/cache'

import { api, type QualityIssue } from './api'
import { createSession, destroySession, readSession, type Session } from './session'

/**
 * Server Actions: every mutation the UI can perform.
 *
 * All of them run on the server with the token from the httpOnly cookie, so
 * the browser can never call the platform APIs directly or forge a tenant id.
 * Each returns a small { error } shape for inline form feedback.
 */

export type FormState = { error: string } | null

type TokenResponse = { access_token: string; tenant_id: string; role: Session['role'] }

function str(form: FormData, key: string): string {
  const value = form.get(key)
  return typeof value === 'string' ? value.trim() : ''
}

export async function signup(_prev: FormState, form: FormData): Promise<FormState> {
  const payload = {
    org_name: str(form, 'org_name'),
    org_slug: str(form, 'org_slug').toLowerCase(),
    email: str(form, 'email'),
    password: str(form, 'password'),
    display_name: str(form, 'display_name'),
    currency: str(form, 'currency') || 'USD',
    sector: str(form, 'sector') || 'other',
  }
  if (!payload.org_name || !payload.org_slug || !payload.email || !payload.password) {
    return { error: 'All fields except your name are required.' }
  }
  if (payload.password.length < 10) {
    return { error: 'Use a password of at least 10 characters.' }
  }

  const result = await api.control<TokenResponse>('/v1/auth/signup', {
    method: 'POST',
    body: JSON.stringify(payload),
    auth: false,
  })
  if (!result.ok) return { error: result.message }

  await createSession({
    token: result.data.access_token,
    tenantId: result.data.tenant_id,
    role: result.data.role,
    email: payload.email,
  })
  redirect('/')
}

export async function updateBusiness(sector: string, currency: string): Promise<FormState> {
  const result = await api.control<unknown>('/v1/tenant', {
    method: 'PATCH',
    body: JSON.stringify({ sector, currency }),
  })
  if (!result.ok) return { error: result.message }

  // Readings already stored keep the band they were judged against, so nothing
  // historical moves — but every page showing a band or a threshold is now
  // stale, and a customer who just changed this expects to see it.
  revalidatePath('/settings')
  revalidatePath('/domains')
  revalidatePath('/')
  return null
}

export async function login(_prev: FormState, form: FormData): Promise<FormState> {
  const email = str(form, 'email')
  const password = str(form, 'password')
  const orgSlug = str(form, 'org_slug')
  if (!email || !password) return { error: 'Email and password are required.' }

  const result = await api.control<TokenResponse>('/v1/auth/login', {
    method: 'POST',
    body: JSON.stringify({
      email,
      password,
      org_slug: orgSlug ? orgSlug.toLowerCase() : null,
    }),
    auth: false,
  })
  if (!result.ok) return { error: result.message }

  await createSession({
    token: result.data.access_token,
    tenantId: result.data.tenant_id,
    role: result.data.role,
    email,
  })
  redirect('/')
}

export async function logout(): Promise<void> {
  await destroySession()
  redirect('/login')
}

export type ResolveState =
  | { ok: true; decision: 'approved' | 'rejected'; action: string }
  | { ok: false; error: string }
  | null

export async function resolveApproval(
  _prev: ResolveState,
  form: FormData,
): Promise<ResolveState> {
  const id = str(form, 'approval_id')
  const decision = str(form, 'decision')
  const label = str(form, 'action_label') || 'Action'
  if (!id || (decision !== 'approved' && decision !== 'rejected')) {
    return { ok: false, error: 'Invalid approval decision.' }
  }

  const session = await readSession()
  if (session?.role !== 'owner') {
    return { ok: false, error: 'Only an owner can resolve approvals.' }
  }

  const result = await api.runtime(`/v1/approvals/${id}/resolve`, {
    method: 'POST',
    body: JSON.stringify({ decision }),
  })
  if (!result.ok) return { ok: false, error: result.message }

  revalidatePath('/approvals')
  revalidatePath('/')
  revalidatePath('/activity')
  // Revalidation removes this card from the list, so the confirmation cannot
  // live in the card itself — the caller raises a toast from this result.
  return { ok: true, decision, action: label }
}

export async function setMonitoring(
  _prev: FormState,
  form: FormData,
): Promise<FormState> {
  const domain = str(form, 'domain')
  const enable = str(form, 'enable') === 'true'
  const interval = Number(str(form, 'interval_minutes') || '60')

  if (!/^[a-z0-9][a-z0-9_-]*$/.test(domain)) {
    return { error: 'Domain keys use lowercase letters, numbers, dashes or underscores.' }
  }
  if (enable && (!Number.isInteger(interval) || interval < 5 || interval > 1440)) {
    return { error: 'Interval must be between 5 and 1440 minutes.' }
  }

  const result = enable
    ? await api.runtime(`/v1/domains/${domain}/monitoring`, {
        method: 'PUT',
        body: JSON.stringify({ interval_minutes: interval }),
      })
    : await api.runtime(`/v1/domains/${domain}/monitoring`, { method: 'DELETE' })

  if (!result.ok) return { error: result.message }

  revalidatePath(`/domains/${domain}`)
  return null
}

export async function pushObservation(
  _prev: FormState,
  form: FormData,
): Promise<FormState> {
  const domain = str(form, 'domain')
  const drift = Number(str(form, 'drift_fraction'))
  const performance = Number(str(form, 'performance'))

  if (!/^[a-z0-9][a-z0-9_-]*$/.test(domain)) {
    return { error: 'Domain keys use lowercase letters, numbers, dashes or underscores.' }
  }
  for (const [label, value] of [
    ['Drift', drift],
    ['Performance', performance],
  ] as const) {
    if (!Number.isFinite(value) || value < 0 || value > 1) {
      return { error: `${label} must be a number between 0 and 1.` }
    }
  }

  const result = await api.runtime(`/v1/domains/${domain}/observations`, {
    method: 'POST',
    body: JSON.stringify({
      drift_fraction: drift,
      performance,
      source: 'dashboard',
    }),
  })
  if (!result.ok) return { error: result.message }

  revalidatePath(`/domains/${domain}`)
  return null
}

export type ReadingState =
  | { ok: true; accepted: boolean; performance?: number; issues: QualityIssue[] }
  | { ok: false; error: string }
  | null

/**
 * Submit a reading in the domain's own metrics. The quality gate's verdict is
 * returned rather than swallowed: a rejected reading is a fact the person
 * entering it needs to see immediately, along with why.
 */
export async function submitReading(
  _prev: ReadingState,
  form: FormData,
): Promise<ReadingState> {
  const domain = str(form, 'domain')
  if (!/^[a-z0-9][a-z0-9_-]*$/.test(domain)) {
    return { ok: false, error: 'Invalid domain key.' }
  }

  // Metric fields are named metric:<key> so the form can be generated from
  // the pack without the action knowing any domain's field names.
  const metrics: Record<string, number> = {}
  for (const [field, raw] of form.entries()) {
    if (!field.startsWith('metric:') || typeof raw !== 'string') continue
    const key = field.slice('metric:'.length)
    const trimmed = raw.trim()
    if (trimmed === '') continue // blank means "not reported", not zero
    const value = Number(trimmed)
    if (!Number.isFinite(value)) {
      return { ok: false, error: `${key} must be a number.` }
    }
    metrics[key] = value
  }

  if (Object.keys(metrics).length === 0) {
    return { ok: false, error: 'Enter at least one metric.' }
  }

  const result = await api.runtime<{
    accepted: boolean
    performance?: number
    issues: QualityIssue[]
  }>(`/v1/domains/${domain}/readings`, {
    method: 'POST',
    body: JSON.stringify({ metrics, source: 'dashboard' }),
  })
  if (!result.ok) return { ok: false, error: result.message }

  revalidatePath(`/domains/${domain}`)
  revalidatePath('/domains')
  return {
    ok: true,
    accepted: result.data.accepted,
    performance: result.data.performance,
    issues: result.data.issues ?? [],
  }
}

export async function evaluateNow(_prev: FormState, form: FormData): Promise<FormState> {
  const domain = str(form, 'domain')
  if (!/^[a-z0-9][a-z0-9_-]*$/.test(domain)) {
    return { error: 'Invalid domain key.' }
  }
  // Runs the full cycle (evaluate → diagnose → notify) through the same
  // durable workflow the schedule uses, so an on-demand run is identical.
  const result = await api.runtime<{ status: string }>(
    `/v1/domains/${domain}/monitor-run`,
    { method: 'POST', body: JSON.stringify({}) },
  )
  if (!result.ok) return { error: result.message }

  revalidatePath(`/domains/${domain}`)
  revalidatePath('/approvals')
  revalidatePath('/')

  if (result.data?.status === 'running') {
    return { error: 'Still analysing — refresh in a moment to see the result.' }
  }
  return null
}

export type IssueKeyState =
  | { ok: true; id: string; name: string; prefix: string; secret: string }
  | { ok: false; error: string }
  | null

/**
 * Mint an ingest key and hand the secret back exactly once.
 *
 * The secret travels through the action result and is deliberately never
 * revalidated into the list: the platform cannot show it again, so the only
 * copy that will ever exist is the one now on screen. The UI is responsible
 * for saying so plainly.
 */
export async function issueApiKey(
  _prev: IssueKeyState,
  form: FormData,
): Promise<IssueKeyState> {
  const name = str(form, 'name')
  if (name.length < 2) {
    return { ok: false, error: 'Give the key a name — you cannot tell keys apart later without one.' }
  }
  if (name.length > 120) {
    return { ok: false, error: 'Keep the name under 120 characters.' }
  }

  const session = await readSession()
  if (session?.role !== 'owner') {
    return { ok: false, error: 'Only an owner can issue an ingest key.' }
  }

  const result = await api.control<{
    id: string
    name: string
    prefix: string
    secret: string
  }>('/v1/api-keys', { method: 'POST', body: JSON.stringify({ name }) })
  if (!result.ok) return { ok: false, error: result.message }

  revalidatePath('/connections')
  return {
    ok: true,
    id: result.data.id,
    name: result.data.name,
    prefix: result.data.prefix,
    secret: result.data.secret,
  }
}

export type RevokeKeyState = { ok: true; name: string } | { ok: false; error: string } | null

export async function revokeApiKey(
  _prev: RevokeKeyState,
  form: FormData,
): Promise<RevokeKeyState> {
  const id = str(form, 'key_id')
  const name = str(form, 'key_name') || 'That key'
  if (!id) return { ok: false, error: 'Invalid key.' }

  const session = await readSession()
  if (session?.role !== 'owner') {
    return { ok: false, error: 'Only an owner can revoke an ingest key.' }
  }

  const result = await api.control(`/v1/api-keys/${id}/revoke`, { method: 'POST' })
  if (!result.ok) return { ok: false, error: result.message }

  revalidatePath('/connections')
  return { ok: true, name }
}
