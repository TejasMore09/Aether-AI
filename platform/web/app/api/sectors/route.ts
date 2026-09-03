import { NextResponse } from 'next/server'

import { api, type SectorOption } from '@/lib/api'

/**
 * The sector catalogue, for the signup form.
 *
 * A route handler rather than a direct fetch from the browser, because this
 * app is a back-end-for-front-end: the browser never learns the platform's
 * hostnames and never holds a token. Signup is the one page where the reader
 * has no account yet, so this is the one place the catalogue is fetched
 * without auth — which is safe precisely because it contains no tenant data,
 * only what the platform can and cannot judge.
 */
export async function GET() {
  const result = await api.control<SectorOption[]>('/v1/sectors', { auth: false })
  if (!result.ok) {
    // An empty list degrades the form to "no sector question" rather than
    // breaking signup. Nobody should be unable to create an account because
    // an optional dropdown could not load.
    return NextResponse.json([], { status: 200 })
  }
  return NextResponse.json(result.data)
}
