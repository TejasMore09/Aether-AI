import Link from 'next/link'
import { redirect } from 'next/navigation'

import { Tag } from '@/components/instrument'
import { brain, type Grant } from '@/lib/api'
import { signOut } from '@/lib/actions'
import { readSession } from '@/lib/session'

import { NavLink } from './NavLink'
import { OpenGrantBar } from './OpenGrantBar'

export default async function ConsoleLayout({ children }: { children: React.ReactNode }) {
  const session = await readSession()
  if (!session) redirect('/login')

  const grants = await brain<Grant[]>('/v1/grants?live=true')

  // A token the cookie still believes in but the brain refuses — rotated
  // staff secret, deactivated account. Hand off to the route handler that can
  // actually clear the cookie.
  if (!grants.ok && grants.status === 401) redirect('/signed-out')

  // Only *this* person's open grants belong in their chrome. Someone else's
  // live grant is information for the trail, not a warning about where the
  // reader currently is.
  const mine = grants.ok ? grants.data.filter((g) => g.admin_email === session.email) : []

  return (
    <div className="min-h-dvh">
      <header
        className="sticky top-0 z-20 border-b"
        style={{ background: 'var(--steel-900)', borderColor: 'var(--line)' }}
      >
        <div className="mx-auto flex max-w-[1320px] flex-wrap items-center gap-5 px-5 py-[10px]">
          <Link href="/" className="flex items-center gap-[10px]" aria-label="Fleet">
            <span
              className="grid h-[22px] w-[22px] place-items-center rounded-[3px] text-[11px] font-bold"
              style={{ background: 'var(--steel-700)', color: 'var(--ink-soft)' }}
              aria-hidden="true"
            >
              Æ
            </span>
            <span
              className="text-[11px] font-semibold uppercase tracking-[0.15em]"
              style={{ color: 'var(--ink-soft)' }}
            >
              Console
            </span>
          </Link>

          <nav className="flex flex-1 items-center gap-1" aria-label="Console">
            <NavLink href="/">Fleet</NavLink>
            <NavLink href="/faults">Faults</NavLink>
            <NavLink href="/trail">Staff trail</NavLink>
          </nav>

          <div className="flex items-center gap-3">
            <span className="text-[12px]" style={{ color: 'var(--ink-faint)' }}>
              {session.email}
            </span>
            <Tag tone={session.role === 'admin' ? 'attention' : 'plain'}>{session.role}</Tag>
            <form action={signOut}>
              <button
                type="submit"
                className="rounded-[4px] border px-[10px] py-[5px] text-[12px] transition-colors duration-150"
                style={{ borderColor: 'var(--line)', color: 'var(--ink-faint)' }}
              >
                Sign out
              </button>
            </form>
          </div>
        </div>
      </header>

      {/* Sticky, full-width, and in a colour used nowhere else. Someone with a
          live grant is inside another company's data; that should follow them
          across every page until they end it. */}
      <OpenGrantBar grants={mine} />

      <main className="mx-auto w-full max-w-[1320px] px-5 py-6">{children}</main>
    </div>
  )
}
