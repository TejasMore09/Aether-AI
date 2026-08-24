import 'server-only'

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
}

const SESSION_MAX_AGE_SECONDS = 60 * 60 // must not outlive the JWT's own TTL

export async function createSession(session: Session): Promise<void> {
  const store = await cookies()
  store.set(SESSION_COOKIE, JSON.stringify(session), {
    httpOnly: true,
    sameSite: 'lax',
    secure: process.env.NODE_ENV === 'production',
    path: '/',
    maxAge: SESSION_MAX_AGE_SECONDS,
  })
}

export async function readSession(): Promise<Session | null> {
  const raw = (await cookies()).get(SESSION_COOKIE)?.value
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw) as Partial<Session>
    if (!parsed.token || !parsed.tenantId || !parsed.role || !parsed.email) {
      return null
    }
    return parsed as Session
  } catch {
    return null // malformed cookie is simply no session
  }
}

export async function destroySession(): Promise<void> {
  ;(await cookies()).delete(SESSION_COOKIE)
}
