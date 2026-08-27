import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

import { SESSION_COOKIE } from '@/lib/session'

/**
 * The escape hatch from a dead session.
 *
 * Cookies cannot be deleted during a Server Component render, so a page that
 * discovers its token is rejected cannot clear it itself. It redirects here
 * instead: a Route Handler may delete the cookie, and then sends the person to
 * sign in. Reached whenever the platform rejects the token for a reason the
 * expiry stamp cannot predict — a rotated signing secret, a revoked account.
 */
export async function GET(request: NextRequest) {
  const url = request.nextUrl.clone()
  url.pathname = '/login'
  url.search = ''

  const response = NextResponse.redirect(url)
  response.cookies.delete(SESSION_COOKIE)
  return response
}
