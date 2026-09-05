'use server'

import { revalidatePath } from 'next/cache'
import { redirect } from 'next/navigation'

import { brain } from './api'
import { createSession, destroySession, readSession, type StaffRole } from './session'

export type FormState = { error: string } | null

function str(form: FormData, key: string): string {
  const value = form.get(key)
  return typeof value === 'string' ? value.trim() : ''
}

export async function signIn(_prev: FormState, form: FormData): Promise<FormState> {
  const email = str(form, 'email')
  const password = str(form, 'password')
  if (!email || !password) return { error: 'Email and password are required.' }

  const result = await brain<{ access_token: string; email: string; role: StaffRole }>(
    '/v1/staff/login',
    { method: 'POST', body: JSON.stringify({ email, password }), auth: false },
  )
  if (!result.ok) return { error: result.message }

  await createSession({
    token: result.data.access_token,
    email: result.data.email,
    role: result.data.role,
  })
  redirect('/')
}

/**
 * Sign out of the console.
 *
 * Drops the cookie and nothing else, which is deliberate rather than an
 * oversight: staff tokens are a separate world with a thirty-minute life and
 * no session table behind them yet. 6.7 gave customer sessions revocation;
 * staff sessions still expire rather than end, and the mitigation is that
 * thirty minutes is short and every break-glass grant is separately
 * revocable. Recorded here so the asymmetry is visible where it matters.
 */
export async function signOut(): Promise<void> {
  await destroySession()
  redirect('/login')
}

export type GrantState =
  | { ok: true; tenantName: string; expiresAt: string }
  | { ok: false; error: string }
  | null

/**
 * Open a break-glass grant.
 *
 * Validated here as well as on the brain, not because the client check adds
 * security — it does not — but because a reason rejected after a round trip
 * is a reason the engineer retypes in a hurry, and hurried reasons are how
 * "debugging" ends up in a customer's permanent record.
 */
export async function openGrant(_prev: GrantState, form: FormData): Promise<GrantState> {
  const tenantId = str(form, 'tenant_id')
  const tenantName = str(form, 'tenant_name') || 'this organization'
  const reason = str(form, 'reason')
  const scope = str(form, 'scope') === 'operate' ? 'operate' : 'read_only'
  const minutes = Number(str(form, 'minutes') || '15')

  if (reason.length < 12) {
    return {
      ok: false,
      error: 'Write a real reason — at least 12 characters. The customer will read this.',
    }
  }
  if (!Number.isInteger(minutes) || minutes < 1 || minutes > 240) {
    return { ok: false, error: 'Duration must be between 1 and 240 minutes.' }
  }

  const session = await readSession()
  if (!session || session.role === 'observer') {
    return { ok: false, error: 'Your staff role cannot open a break-glass grant.' }
  }

  const result = await brain<{ expires_at: string }>('/v1/grants', {
    method: 'POST',
    body: JSON.stringify({ tenant_id: tenantId, reason, scope, minutes }),
  })
  if (!result.ok) return { ok: false, error: result.message }

  // Targeted, not revalidatePath('/', 'layout'). Revalidating the root layout
  // invalidates the whole route tree and lands the router back on /, throwing
  // the engineer out of the tenant they just opened access to.
  revalidatePath(`/tenants/${tenantId}`)
  revalidatePath('/')
  return { ok: true, tenantName, expiresAt: result.data.expires_at }
}

export type EndGrantState = { ok: true } | { ok: false; error: string } | null

export async function endGrant(_prev: EndGrantState, form: FormData): Promise<EndGrantState> {
  const grantId = str(form, 'grant_id')
  const tenantId = str(form, 'tenant_id')
  if (!grantId) return { ok: false, error: 'Invalid grant.' }

  const result = await brain(`/v1/grants/${grantId}/end`, { method: 'POST' })
  if (!result.ok) return { ok: false, error: result.message }

  if (tenantId) revalidatePath(`/tenants/${tenantId}`)
  revalidatePath('/')
  revalidatePath('/trail')
  return { ok: true }
}


/**
 * Mark a fault handled, which re-arms its alarm.
 *
 * Not cosmetic. An unresolved fault keeps its alert timestamp, so one that was
 * fixed and returns weeks later would be folded into a row that has already
 * alerted and nobody would hear about it.
 */
export async function resolveFault(fingerprint: string): Promise<FormState> {
  const result = await brain<{ status: string }>(
    `/v1/ops/errors/${encodeURIComponent(fingerprint)}/resolve`,
    { method: 'POST' },
  )
  if (!result.ok) return { error: result.message }
  revalidatePath('/faults')
  return null
}
