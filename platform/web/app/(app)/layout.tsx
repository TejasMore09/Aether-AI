import Link from 'next/link'
import { redirect } from 'next/navigation'

import { NavLink } from '@/components/NavLink'
import { api, type TenantInfo } from '@/lib/api'
import { logout } from '@/lib/actions'
import { readSession } from '@/lib/session'

const NAV = [
  { href: '/', label: 'Overview' },
  { href: '/approvals', label: 'Approvals' },
  { href: '/domains', label: 'Domains' },
  { href: '/catalogue', label: 'Catalogue' },
  { href: '/connections', label: 'Connections' },
  { href: '/activity', label: 'Activity' },
  { href: '/usage', label: 'AI usage' },
]

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const session = await readSession()
  if (!session) redirect('/login')

  const tenant = await api.control<TenantInfo>('/v1/tenant')

  // The token is present and unexpired but the platform will not accept it —
  // a rotated signing secret, a revoked account. Clearing the cookie needs a
  // Route Handler, so hand off to one rather than rendering a shell whose
  // every panel reads "your session expired" with no way to act on it.
  if (!tenant.ok && tenant.status === 401) redirect('/signed-out')

  const orgName = tenant.ok ? tenant.data.name : 'Organization'

  return (
    <div className="relative min-h-dvh overflow-x-hidden">
      {/* A single still copper bloom. Static by design — ambient looping
          motion is the clearest tell of a generated interface. */}
      <div
        aria-hidden="true"
        className="pointer-events-none fixed -right-40 -top-56 -z-10 h-[620px] w-[620px] rounded-full"
        style={{
          background:
            'radial-gradient(circle, rgba(201,138,75,0.13), transparent 68%)',
        }}
      />

      <header className="flex flex-wrap items-center gap-6 px-6 py-5 md:px-11">
        <Link href="/" className="flex items-center gap-3" aria-label="Aether home">
          <span
            className="relative grid h-[30px] w-[30px] place-items-center rounded-[10px]"
            style={{ background: 'var(--color-raised)', boxShadow: 'var(--raise-sm)' }}
            aria-hidden="true"
          >
            <span
              className="block h-3 w-3 rounded-[3px]"
              style={{
                background:
                  'linear-gradient(145deg, var(--color-copper), var(--color-copper-dim))',
              }}
            />
          </span>
          <span className="text-base font-bold tracking-[-0.015em]">Aether</span>
        </Link>

        <nav className="flex flex-1 flex-wrap gap-2" aria-label="Main">
          {NAV.map((item) => (
            <NavLink key={item.href} href={item.href}>
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="flex items-center gap-3">
          <span
            className="flex items-center gap-[9px] rounded-[12px] px-[15px] py-2 text-[13.5px]"
            style={{
              background: 'var(--color-raised)',
              boxShadow: 'var(--raise-sm)',
              color: 'var(--color-ink-soft)',
            }}
            title={session.email}
          >
            <span
              className="h-[7px] w-[7px] rounded-full"
              style={{ background: 'var(--color-good)' }}
              aria-hidden="true"
            />
            {orgName}
          </span>
          <form action={logout}>
            <button
              type="submit"
              className="rounded-[12px] px-4 py-2 text-[13.5px] font-medium transition-colors duration-200"
              style={{
                background: 'var(--color-raised)',
                boxShadow: 'var(--raise-sm)',
                color: 'var(--color-ink-faint)',
              }}
            >
              Sign out
            </button>
          </form>
        </div>
      </header>

      <main className="mx-auto w-full max-w-[1180px] px-6 pb-28 pt-2 md:px-11">
        {children}
      </main>
    </div>
  )
}
