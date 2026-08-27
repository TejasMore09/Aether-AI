import { NextResponse } from 'next/server'
import type { NextRequest } from 'next/server'

import { SESSION_COOKIE, parseSession } from './lib/session'

/**
 * Optimistic gate. Real authorization is the main brain's, on every request.
 *
 * Note what is absent: this console has no public surface at all. There is no
 * equivalent of the customer app's /explore, because there is nothing here a
 * stranger has any business seeing.
 */
const AUTH_PATHS = ['/login']

const matches = (paths: string[], pathname: string) =>
  paths.some((p) => pathname === p || pathname.startsWith(`${p}/`))

export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl
  const signedIn = parseSession(request.cookies.get(SESSION_COOKIE)?.value) !== null

  if (!signedIn && !matches(AUTH_PATHS, pathname)) {
    const url = request.nextUrl.clone()
    url.pathname = '/login'
    url.search = ''
    return NextResponse.redirect(url)
  }

  if (signedIn && matches(AUTH_PATHS, pathname)) {
    const url = request.nextUrl.clone()
    url.pathname = '/'
    url.search = ''
    return NextResponse.redirect(url)
  }

  return NextResponse.next()
}

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico).*)'],
}
