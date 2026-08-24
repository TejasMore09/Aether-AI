import Link from 'next/link'
import { redirect } from 'next/navigation'

import { api, type TenantInfo } from '@/lib/api'
import { logout } from '@/lib/actions'
import { readSession } from '@/lib/session'

const NAV = [
  { href: '/', label: 'Overview' },
  { href: '/approvals', label: 'Approvals' },
  { href: '/domains', label: 'Domains' },
  { href: '/activity', label: 'Activity' },
  { href: '/usage', label: 'AI Usage' },
]

export default async function AppLayout({ children }: { children: React.ReactNode }) {
  const session = await readSession()
  if (!session) redirect('/login')

  const tenant = await api.control<TenantInfo>('/v1/tenant')
  const orgName = tenant.ok ? tenant.data.name : 'Organization'

  return (
    <div style={{ display: 'flex', minHeight: '100vh' }}>
      <nav
        style={{
          width: 232,
          flexShrink: 0,
          borderRight: '1px solid var(--color-line)',
          background: 'var(--color-surface)',
          display: 'flex',
          flexDirection: 'column',
          position: 'sticky',
          top: 0,
          height: '100vh',
        }}
      >
        <div style={{ padding: '22px 20px', borderBottom: '1px solid var(--color-line)' }}>
          <div className="label" style={{ color: 'var(--color-accent)' }}>
            Aether Nano
          </div>
          <div
            style={{
              fontSize: 15,
              fontWeight: 600,
              marginTop: 8,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
            title={orgName}
          >
            {orgName}
          </div>
          <div className="mono" style={{ fontSize: 11, color: 'var(--color-ink-faint)', marginTop: 2 }}>
            {session.role}
          </div>
        </div>

        <div style={{ flex: 1, padding: '12px 0' }}>
          {NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="mono"
              style={{
                display: 'block',
                padding: '11px 20px',
                fontSize: 12,
                letterSpacing: '0.06em',
                textTransform: 'uppercase',
                color: 'var(--color-ink-muted)',
              }}
            >
              {item.label}
            </Link>
          ))}
        </div>

        <div style={{ padding: 20, borderTop: '1px solid var(--color-line)' }}>
          <div
            style={{
              fontSize: 12,
              color: 'var(--color-ink-faint)',
              marginBottom: 12,
              overflow: 'hidden',
              textOverflow: 'ellipsis',
            }}
            title={session.email}
          >
            {session.email}
          </div>
          <form action={logout}>
            <button type="submit" className="btn btn-ghost" style={{ width: '100%' }}>
              Sign out
            </button>
          </form>
        </div>
      </nav>

      <main style={{ flex: 1, padding: '36px 40px', maxWidth: 1180 }}>{children}</main>
    </div>
  )
}
