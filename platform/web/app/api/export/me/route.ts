import { NextResponse } from 'next/server'

import { api } from '@/lib/api'

/**
 * A portability export, fetched server-side and handed to the browser.
 *
 * A route handler rather than a direct call, for the same reason as every
 * other read in this application: the browser holds no token and never learns
 * the platform's hostnames. The file is assembled here and streamed on.
 */
export async function GET() {
  const result = await api.control<unknown>('/v1/me/export')
  if (!result.ok) {
    return NextResponse.json({ error: result.message }, { status: result.status || 500 })
  }
  return NextResponse.json(result.data)
}
