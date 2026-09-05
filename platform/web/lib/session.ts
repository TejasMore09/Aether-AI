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
  /**
   * Epoch ms after which this cookie is treated as dead here.
   *
   * A local guess, not the authority. Since 6.7 the platform can end a session
   * at any moment — a password reset, a sign-out elsewhere, a deactivated
   * account — so a cookie that has not reached this stamp may still be
   * refused. That path is handled: the API returns 401 and the app redirects
   * to /signed-out, which is the only place a cookie can be deleted.
   */
  expiresAt: number
}

// Fourteen days, matching the platform's idle session window.
//
// This was an hour, because that was the JWT's whole life and a cookie
// outliving its token traps somebody on a dashboard whose every request 401s.
// Since 6.7 the session is a row that slides forward with use and can be ended
// from the server, so the cookie no longer has to be the short one — and being
// signed out every hour was the "support burden at scale" the plan named.
const SESSION_MAX_AGE_SECONDS = 60 * 60 * 24 * 14

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
