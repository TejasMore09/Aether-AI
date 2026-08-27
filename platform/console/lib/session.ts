import { cookies } from 'next/headers'

/**
 * Staff session.
 *
 * A different cookie name from the customer dashboard's, so the two can be
 * served from the same hostname during development without either one
 * shadowing the other — and so a stray cookie from one is never even
 * syntactically valid to the other.
 *
 * Short-lived by design: staff sessions exist to work an incident, not to sit
 * open all day. The cookie must never outlive the token it carries.
 */

export const SESSION_COOKIE = 'aether_staff_session'

export type StaffRole = 'observer' | 'engineer' | 'admin'

export type StaffSession = {
  token: string
  email: string
  role: StaffRole
  /** Epoch ms when the main brain stops accepting this token. */
  expiresAt: number
}

// Matches AETHER_STAFF_JWT_TTL_MINUTES (30) on the brain.
const SESSION_MAX_AGE_SECONDS = 30 * 60

export async function createSession(
  session: Omit<StaffSession, 'expiresAt'>,
): Promise<void> {
  const store = await cookies()
  const withExpiry: StaffSession = {
    ...session,
    expiresAt: Date.now() + SESSION_MAX_AGE_SECONDS * 1000,
  }
  store.set(SESSION_COOKIE, JSON.stringify(withExpiry), {
    httpOnly: true,
    sameSite: 'strict', // stricter than the customer app: no cross-site navigation should carry a staff session
    secure: process.env.NODE_ENV === 'production',
    path: '/',
    maxAge: SESSION_MAX_AGE_SECONDS,
  })
}

/** Parse a raw cookie value into a session, or null. Shared with the proxy. */
export function parseSession(raw: string | undefined): StaffSession | null {
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw) as Partial<StaffSession>
    if (!parsed.token || !parsed.email || !parsed.role) return null
    if (typeof parsed.expiresAt === 'number' && Date.now() >= parsed.expiresAt) {
      return null
    }
    return parsed as StaffSession
  } catch {
    return null
  }
}

export async function readSession(): Promise<StaffSession | null> {
  return parseSession((await cookies()).get(SESSION_COOKIE)?.value)
}

export async function destroySession(): Promise<void> {
  ;(await cookies()).delete(SESSION_COOKIE)
}

const RANK: Record<StaffRole, number> = { observer: 0, engineer: 1, admin: 2 }

export function atLeast(role: StaffRole, minimum: StaffRole): boolean {
  return RANK[role] >= RANK[minimum]
}
