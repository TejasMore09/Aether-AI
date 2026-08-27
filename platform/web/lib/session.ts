import { cookies } from 'next/headers'

/**
 * Session handling for the BFF pattern.
 *
 * The platform JWT is stored in an httpOnly cookie, so it is never readable
 * from JavaScript (no XSS token theft) and never shipped to the browser
 * bundle. Every API call is made server-side with the token read from here.
 */

export const SESSION_COOKIE = 'aether_session'

export type Session = {
  token: string
  tenantId: string
  role: 'owner' | 'operator' | 'viewer'
  email: string
  /** Epoch ms when the platform JWT stops being accepted. */
  expiresAt: number
}

const SESSION_MAX_AGE_SECONDS = 60 * 60 // must not outlive the JWT's own TTL

export async function createSession(
  session: Omit<Session, 'expiresAt'>,
): Promise<void> {
  const store = await cookies()
  const withExpiry: Session = {
    ...session,
    expiresAt: Date.now() + SESSION_MAX_AGE_SECONDS * 1000,
  }
  store.set(SESSION_COOKIE, JSON.stringify(withExpiry), {
    httpOnly: true,
    sameSite: 'lax',
    secure: process.env.NODE_ENV === 'production',
    path: '/',
    maxAge: SESSION_MAX_AGE_SECONDS,
  })
}

/**
 * Parse a raw cookie value into a session, or null.
 *
 * Shared with the proxy, which cannot import server-only code — hence the
 * plain function taking a string rather than reading cookies() itself.
 */
export function parseSession(raw: string | undefined): Session | null {
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw) as Partial<Session>
    if (!parsed.token || !parsed.tenantId || !parsed.role || !parsed.email) {
      return null
    }
    // An expired session is no session. Without this the cookie outlives the
    // token it carries: the proxy sees "signed in", every API call returns
    // 401, and the redirect away from /login traps the user on a dashboard
    // that cannot load with no way back to signing in.
    if (typeof parsed.expiresAt === 'number' && Date.now() >= parsed.expiresAt) {
      return null
    }
    return parsed as Session
  } catch {
    return null // malformed cookie is simply no session
  }
}

export async function readSession(): Promise<Session | null> {
  return parseSession((await cookies()).get(SESSION_COOKIE)?.value)
}

export async function destroySession(): Promise<void> {
  ;(await cookies()).delete(SESSION_COOKIE)
}
