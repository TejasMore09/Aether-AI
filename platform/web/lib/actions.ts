'use server'

import { redirect } from 'next/navigation'
import { revalidatePath } from 'next/cache'

import { api } from './api'
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

export async function resolveApproval(
  _prev: FormState,
  form: FormData,
): Promise<FormState> {
  const id = str(form, 'approval_id')
  const decision = str(form, 'decision')
  if (!id || (decision !== 'approved' && decision !== 'rejected')) {
    return { error: 'Invalid approval decision.' }
  }

  const session = await readSession()
  if (session?.role !== 'owner') {
    return { error: 'Only an owner can resolve approvals.' }
  }

  const result = await api.runtime(`/v1/approvals/${id}/resolve`, {
    method: 'POST',
    body: JSON.stringify({ decision }),
  })
  if (!result.ok) return { error: result.message }

  revalidatePath('/approvals')
  revalidatePath('/')
  return null
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
