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

/**
 * Password reset needs a third answer. Its whole design is that requesting a
 * link succeeds identically whether or not the address exists, so there is no
 * error to report and no data to show — only reassurance. Kept separate from
 * `FormState` because no other action here can produce one, and widening the
 * shared type would have made every caller narrow for a case it cannot hit.
 */
export type AuthFormState = FormState | { notice: string }

/**
 * A password accepted, and a session deliberately withheld.
 *
 * Carried back to the login page so it can ask for a code. The email rides
 * along only so the second step can say whose account it is asking about.
 */
export type MfaPending = { mfaChallenge: string; email: string }

export type LoginState = FormState | MfaPending

type MfaChallenge = { mfa_required: true; challenge: string; tenant_id: string }

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

/**
 * Finish a sign-in that stopped for a second factor.
 *
 * The challenge is passed back through a hidden field rather than kept in a
 * cookie: it is a half-identity with a five-minute life, and putting it
 * anywhere durable would be storing exactly the thing that must not outlive
 * the form it belongs to.
 */
export async function completeSignIn(_prev: LoginState, form: FormData): Promise<LoginState> {
  const challenge = str(form, 'challenge')
  const code = str(form, 'code')
  if (!code) return { error: 'Enter the code from your authenticator app.' }

  const result = await api.control<TokenResponse>('/v1/auth/mfa/verify', {
    method: 'POST',
    body: JSON.stringify({ challenge, code }),
    auth: false,
  })
  if (!result.ok) {
    // The challenge is still good for a few minutes, so the page keeps asking
    // rather than sending somebody back to type their password again.
    return result.status === 401 && !result.message.includes('again')
      ? { mfaChallenge: challenge, email: str(form, 'email'), error: result.message }
      : { error: result.message }
  }

  await createSession({
    token: result.data.access_token,
    tenantId: result.data.tenant_id,
    role: result.data.role,
    email: str(form, 'email'),
  })
  redirect('/')
}

// ── The second factor, from the settings page ─────────────────────────────────

export type MfaStatus = {
  enrolled: boolean
  confirmed: boolean
  recovery_codes_left: number
  available: boolean
}

export type EnrolState =
  | { secret: string; otpauth_uri: string }
  | { recoveryCodes: string[] }
  | { error: string }
  | null

export async function startMfaEnrolment(): Promise<EnrolState> {
  const result = await api.control<{ secret: string; otpauth_uri: string }>('/v1/auth/mfa/enrol', {
    method: 'POST',
  })
  return result.ok ? result.data : { error: result.message }
}

/**
 * Prove the authenticator works and receive the recovery codes.
 *
 * They are returned once and never again. Without them a lost phone is a lost
 * account, so the page that shows them has to make that clear.
 */
export async function confirmMfaEnrolment(code: string): Promise<EnrolState> {
  const result = await api.control<{ recovery_codes: string[] }>('/v1/auth/mfa/confirm', {
    method: 'POST',
    body: JSON.stringify({ code }),
  })
  if (!result.ok) return { error: result.message }
  revalidatePath('/settings')
  return { recoveryCodes: result.data.recovery_codes }
}

export async function disableMfa(code: string): Promise<FormState> {
  const result = await api.control<void>('/v1/auth/mfa/disable', {
    method: 'POST',
    body: JSON.stringify({ code }),
  })
  if (!result.ok) return { error: result.message }
  revalidatePath('/settings')
  return null
}

// ── Your data ─────────────────────────────────────────────────────────────────

/**
 * Erase yourself.
 *
 * On success the session is gone on the platform's side, so the cookie is
 * dropped here too and the person lands on a page that no longer knows them.
 * Leaving them on a dashboard whose every request 401s would be the worse
 * ending.
 */
export async function eraseMe(password: string, confirm: string): Promise<FormState> {
  const result = await api.control<{ erased: boolean }>('/v1/me/erase', {
    method: 'POST',
    body: JSON.stringify({ password, confirm }),
  })
  if (!result.ok) return { error: result.message }
  await destroySession()
  redirect('/login')
}

export async function eraseOrganisation(
  password: string,
  confirmSlug: string,
): Promise<FormState> {
  const result = await api.control<{ erased: boolean }>('/v1/tenant/erase', {
    method: 'POST',
    body: JSON.stringify({ password, confirm_slug: confirmSlug }),
  })
  if (!result.ok) return { error: result.message }
  // The organisation is gone, so the session pointing at it is meaningless.
  await destroySession()
  redirect('/login')
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

/**
 * Ask for a reset link.
 *
 * Always reports the same thing. The API is careful never to say whether an
 * address has an account, and a UI that helpfully rendered "no such user"
 * would hand back the exact fact the API withheld — the leak would be here,
 * not there.
 */
export async function forgotPassword(
  _prev: AuthFormState,
  form: FormData,
): Promise<AuthFormState> {
  const email = str(form, 'email')
  if (!email) return { error: 'Enter the email address you sign in with.' }

  const result = await api.control<{ detail: string }>('/v1/auth/forgot', {
    method: 'POST',
    body: JSON.stringify({ email }),
    auth: false,
  })
  // Rate limiting is the one refusal worth surfacing: it is about the caller,
  // not about whether the account exists.
  if (!result.ok && result.status === 429) return { error: result.message }

  return {
    notice:
      'If that address has an account, a reset link is on its way. ' +
      'It expires in 45 minutes, and asking again replaces it.',
  }
}

export async function resetPassword(_prev: FormState, form: FormData): Promise<FormState> {
  const token = str(form, 'token')
  const password = str(form, 'password')
  if (!token) return { error: 'That link is incomplete. Request a new one.' }
  if (password.length < 10) return { error: 'Use a password of at least 10 characters.' }
  if (password !== str(form, 'confirm')) return { error: 'The two passwords do not match.' }

  const result = await api.control<{ detail: string }>('/v1/auth/reset', {
    method: 'POST',
    body: JSON.stringify({ token, password }),
    auth: false,
  })
  if (!result.ok) return { error: result.message }

  // Deliberately not signed in here. Completing a reset proves control of the
  // mailbox, not of the account, and the password just set is the thing that
  // proves the second — so it gets used once, immediately.
  redirect('/login?reset=1')
}

export async function login(_prev: LoginState, form: FormData): Promise<LoginState> {
  const email = str(form, 'email')
  const password = str(form, 'password')
  const orgSlug = str(form, 'org_slug')
  if (!email || !password) return { error: 'Email and password are required.' }

  const result = await api.control<TokenResponse | MfaChallenge>('/v1/auth/login', {
    method: 'POST',
    body: JSON.stringify({
      email,
      password,
      org_slug: orgSlug ? orgSlug.toLowerCase() : null,
    }),
    auth: false,
  })
  if (!result.ok) return { error: result.message }

  // A correct password is not a session when there is a second factor. The
  // challenge is handed to the page, which asks for a code — it carries no
  // session and nothing else on the platform accepts it.
  if ('mfa_required' in result.data) {
    return { mfaChallenge: result.data.challenge, email }
  }

  await createSession({
    token: result.data.access_token,
    tenantId: result.data.tenant_id,
    role: result.data.role,
    email,
  })
  redirect('/')
}

/**
 * Sign out, on the platform as well as in this browser.
 *
 * Dropping the cookie was the whole of this before 6.7, which meant signing
 * out ended nothing: the token stayed valid for the rest of its life, so
 * anyone holding a copy still had the account. Telling the platform is the
 * part that matters and the cookie is the cosmetic half.
 *
 * The API call is allowed to fail. If it does, the session is still live and
 * that is bad, but leaving the person signed in *here* as well would be worse
 * — they asked to leave, and the cookie is the only half this side controls.
 */
export async function logout(): Promise<void> {
  await api.control<void>('/v1/auth/logout', { method: 'POST' })
  await destroySession()
  redirect('/login')
}

/**
 * End every other session. What "I think someone else is in my account" needs,
 * and the reason it keeps this one is that the alternative signs you out on
 * the machine you were worried about and asks for your password there.
 */
export async function signOutEverywhereElse(): Promise<FormState> {
  const result = await api.control<{ ended: number }>('/v1/auth/logout-all', { method: 'POST' })
  if (!result.ok) return { error: result.message }
  revalidatePath('/settings')
  return null
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
