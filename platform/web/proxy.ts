import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

import { SESSION_COOKIE, parseSession } from './lib/session'

/**
 * Next.js 16 renamed Middleware to Proxy — same mechanism, new file convention.
 *
 * This is an *optimistic* gate only: it redirects requests with no session
 * cookie to /login so unauthenticated users never see a dashboard shell. Real
 * authorization happens server-side on every request, where the platform APIs
 * validate the JWT and Postgres RLS scopes the data.
 */

/**
 * Reachable without a session.
 *
 * /explore is the public surface — a worked example on mock data, no API calls
 * and no tenant data — so a stranger can judge the product without an account.
 *
 * /api/sectors is the sector catalogue the signup form needs before anyone has
 * an account. It is safe to expose for the same reason /explore is: it holds
 * no tenant data at all, only what the platform can and cannot judge. Adding a
 * path here is a decision about disclosure, not convenience — check that the
 * thing behind it is genuinely tenant-free before extending this list.
 */
const PUBLIC_PATHS = ['/login', '/signup', '/forgot', '/reset', '/explore', '/api/sectors']

/**
 * Public *and* pointless once signed in, so a session bounces away from them.
 *
 * Deliberately narrower than PUBLIC_PATHS: /explore is a demo, not a login
 * page, and a signed-in user following a shared link to it should still see
 * it rather than being thrown into their dashboard.
 */
const AUTH_PATHS = ['/login', '/signup']

const matches = (paths: string[], pathname: string) =>
  paths.some((p) => pathname === p || pathname.startsWith(`${p}/`))

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl
  // Validity, not mere presence. A cookie can outlive the token it carries;
  // treating that as "signed in" is what previously trapped users on a
  // dashboard whose every request 401s, with /login bouncing them back.
  const hasSession = parseSession(request.cookies.get(SESSION_COOKIE)?.value) !== null

  if (!hasSession && !matches(PUBLIC_PATHS, pathname)) {
    const url = request.nextUrl.clone()
    url.pathname = '/login'
    url.search = ''
    return NextResponse.redirect(url)
  }

  if (hasSession && matches(AUTH_PATHS, pathname)) {
    const url = request.nextUrl.clone()
    url.pathname = '/'
    url.search = ''
    return NextResponse.redirect(url)
  }

  return NextResponse.next()
}

export const config = {
  // Skip static assets and Next internals.
  matcher: ['/((?!_next/static|_next/image|favicon.ico).*)'],
}
