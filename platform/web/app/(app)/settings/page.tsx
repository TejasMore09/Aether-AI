import { ErrorNote, PageTitle, Panel, SectionTitle } from '@/components/forge'
import { api, type SectorOption, type TenantInfo } from '@/lib/api'
import { readSession } from '@/lib/session'

import { BusinessForm } from './BusinessForm'

export const metadata = { title: 'Settings · Aether' }

export default async function SettingsPage() {
  const session = await readSession()
  const [tenant, sectors] = await Promise.all([
    api.control<TenantInfo>('/v1/tenant'),
    api.control<SectorOption[]>('/v1/sectors', { auth: false }),
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
    </>
  )
}
