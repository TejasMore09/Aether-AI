'use server'

import { revalidatePath } from 'next/cache'
import { redirect } from 'next/navigation'

import { brain } from './api'
import { createSession, destroySession, readSession, type StaffRole } from './session'

export type FormState = { error: string } | null

/**
 * A staff password accepted, and a session deliberately withheld.
 *
 * A staff credential reaches every tenant on the platform, which is why this
 * surface got a second factor before the customer one needed it.
 */
export type MfaPending = { mfaChallenge: string; email: string }

export type SignInState = FormState | MfaPending

type StaffToken = { access_token: string; email: string; role: StaffRole }
type StaffChallenge = { mfa_required: true; challenge: string }

function str(form: FormData, key: string): string {
  const value = form.get(key)
  return typeof value === 'string' ? value.trim() : ''
}

export async function signIn(_prev: SignInState, form: FormData): Promise<SignInState> {
  const email = str(form, 'email')
  const password = str(form, 'password')
  if (!email || !password) return { error: 'Email and password are required.' }

  const result = await brain<StaffToken | StaffChallenge>('/v1/staff/login', {
    method: 'POST',
    body: JSON.stringify({ email, password }),
    auth: false,
  })
  if (!result.ok) return { error: result.message }

  if ('mfa_required' in result.data) {
    return { mfaChallenge: result.data.challenge, email }
  }

  await createSession({
    token: result.data.access_token,
    email: result.data.email,
    role: result.data.role,
  })
  redirect('/')
}

/** Finish a staff sign-in that stopped for a code. */
export async function completeSignIn(_prev: SignInState, form: FormData): Promise<SignInState> {
  const challenge = str(form, 'challenge')
  const code = str(form, 'code')
  if (!code) return { error: 'Enter the code from your authenticator app.' }

  const result = await brain<StaffToken>('/v1/staff/mfa/verify', {
    method: 'POST',
    body: JSON.stringify({ challenge, code }),
    auth: false,
  })
  if (!result.ok) {
    return result.status === 401 && !result.message.includes('again')
      ? { mfaChallenge: challenge, email: str(form, 'email') }
      : { error: result.message }
  }

  await createSession({
    token: result.data.access_token,
    email: result.data.email,
    role: result.data.role,
  })
  redirect('/')
}

// ── Enrolling, from the console ───────────────────────────────────────────────

export type StaffMfaStatus = {
  enrolled: boolean
  confirmed: boolean
  recovery_codes_left: number
  available: boolean
}

export async function startStaffMfa(): Promise<
  { secret: string; otpauth_uri: string } | { error: string }
> {
  const result = await brain<{ secret: string; otpauth_uri: string }>('/v1/staff/mfa/enrol', {
    method: 'POST',
  })
  return result.ok ? result.data : { error: result.message }
}

export async function confirmStaffMfa(
  code: string,
): Promise<{ recoveryCodes: string[] } | { error: string }> {
  const result = await brain<{ recovery_codes: string[] }>('/v1/staff/mfa/confirm', {
    method: 'POST',
    body: JSON.stringify({ code }),
  })
  if (!result.ok) return { error: result.message }
  revalidatePath('/')
  return { recoveryCodes: result.data.recovery_codes }
}

export async function disableStaffMfa(code: string): Promise<FormState> {
  const result = await brain<void>('/v1/staff/mfa/disable', {
    method: 'POST',
    body: JSON.stringify({ code }),
  })
  if (!result.ok) return { error: result.message }
  revalidatePath('/')
  return null
}

/**
 * Sign out of the console, on the brain as well as in this browser.
 *
 * Dropping the cookie was the whole of this until 6.6, and it ended nothing:
 * the token stayed valid, and a staff token reaches every tenant on the
 * platform. The API call is the part that matters; the cookie is the
 * cosmetic half and is cleared either way, because somebody who asked to
 * leave should leave.
 */
export async function signOut(): Promise<void> {
  await brain<void>('/v1/staff/logout', { method: 'POST' })
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
