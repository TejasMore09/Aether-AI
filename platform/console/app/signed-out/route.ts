import { NextResponse } from 'next/server'

import { SESSION_COOKIE } from '@/lib/session'

/**
 * Clearing a cookie needs a Route Handler, not a Server Component.
 *
 * Reached when the brain refuses a token the cookie still considers valid — a
 * rotated staff secret, a deactivated account. Without this the console
 * renders a shell whose every panel reads "session expired" and whose /login
 * bounces the reader straight back into it.
 */
export function GET(request: Request) {
  const response = NextResponse.redirect(new URL('/login', request.url))
  response.cookies.delete(SESSION_COOKIE)
  return response
}
