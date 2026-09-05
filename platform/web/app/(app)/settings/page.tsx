import { ErrorNote, PageTitle, Panel, SectionTitle } from '@/components/forge'
import { api, type SectorOption, type TenantInfo } from '@/lib/api'
import type { MfaStatus } from '@/lib/actions'
import { readSession } from '@/lib/session'

import { BusinessForm } from './BusinessForm'
import { SecondFactor } from './SecondFactor'
import { SessionList, type SessionRow } from './SessionList'

export const metadata = { title: 'Settings · Aether' }

export default async function SettingsPage() {
  const session = await readSession()
  const [tenant, sectors, mySessions, mfa] = await Promise.all([
    api.control<TenantInfo>('/v1/tenant'),
    api.control<SectorOption[]>('/v1/sectors', { auth: false }),
    api.control<SessionRow[]>('/v1/auth/sessions'),
    api.control<MfaStatus>('/v1/auth/mfa'),
  ])

  if (!tenant.ok) {
    return (
      <>
        <PageTitle title="Settings" />
        <ErrorNote message={tenant.message} />
      </>
    )
  }

  return (
    <>
      <PageTitle
        title="Settings"
        lede={`${tenant.data.name} · ${tenant.data.slug}`}
      />

      <Panel className="mb-5">
        <div className="flex items-baseline justify-between px-4 pt-4">
          <SectionTitle>Your business</SectionTitle>
          <span className="text-[11.5px]" style={{ color: 'var(--color-ink-faint)' }}>
            affects how every reading is judged
          </span>
        </div>
        {sectors.ok ? (
          <BusinessForm
            sectors={sectors.data}
            currentSector={tenant.data.sector}
            currentCurrency={tenant.data.currency}
            canEdit={session?.role === 'owner'}
          />
        ) : (
          <ErrorNote message={sectors.message} />
        )}
      </Panel>

      <Panel className="mb-5">
        <div className="flex items-baseline justify-between px-4 pt-4">
          <SectionTitle>Two-factor authentication</SectionTitle>
          <span className="text-[11.5px]" style={{ color: 'var(--color-ink-faint)' }}>
            a stolen password stops being enough
          </span>
        </div>
        {mfa.ok ? <SecondFactor status={mfa.data} /> : <ErrorNote message={mfa.message} />}
      </Panel>

      <Panel>
        <div className="flex items-baseline justify-between px-4 pt-4">
          <SectionTitle>Where you are signed in</SectionTitle>
          <span className="text-[11.5px]" style={{ color: 'var(--color-ink-faint)' }}>
            signing out ends a session immediately
          </span>
        </div>
        {mySessions.ok ? (
          <SessionList sessions={mySessions.data} />
        ) : (
          <ErrorNote message={mySessions.message} />
        )}
      </Panel>
    </>
  )
}
