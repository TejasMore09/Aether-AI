import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

import { SESSION_COOKIE } from './lib/session'

/**
 * Next.js 16 renamed Middleware to Proxy — same mechanism, new file convention.
 *
 * This is an *optimistic* gate only: it redirects requests with no session
 * cookie to /login so unauthenticated users never see a dashboard shell. Real
 * authorization happens server-side on every request, where the platform APIs
 * validate the JWT and Postgres RLS scopes the data.
 */

const PUBLIC_PATHS = ['/login', '/signup']

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl
  const hasSession = request.cookies.has(SESSION_COOKIE)
  const isPublic = PUBLIC_PATHS.some((p) => pathname === p || pathname.startsWith(`${p}/`))

  if (!hasSession && !isPublic) {
    const url = request.nextUrl.clone()
    url.pathname = '/login'
    url.search = ''
    return NextResponse.redirect(url)
  }

  if (hasSession && isPublic) {
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
