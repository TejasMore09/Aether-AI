import { ErrorNote, PageHead, Panel, PanelHead } from '@/components/instrument'
import { brain } from '@/lib/api'
import type { StaffMfaStatus } from '@/lib/actions'

import { StaffSecondFactor } from './StaffSecondFactor'

export const metadata = { title: 'Your security · Aether Console' }

/**
 * Your own account, not the fleet's.
 *
 * A short page on purpose. The one thing on it is the one thing that matters
 * about a staff account: a password that reaches every tenant on the platform
 * is not, by itself, enough.
 */
export default async function SecurityPage() {
  const status = await brain<StaffMfaStatus>('/v1/staff/mfa')

  return (
    <>
      <PageHead
        title="Your security"
        lede="A staff credential reaches every customer on the platform. That is why this page exists here before it was needed anywhere else."
      />

      <Panel>
        <PanelHead
          title="Two-factor authentication"
          aside={
            <span className="text-[11.5px]" style={{ color: 'var(--ink-faint)' }}>
              enabling and disabling are both recorded
            </span>
          }
        />
        {status.ok ? (
          <StaffSecondFactor status={status.data} />
        ) : (
          <ErrorNote message={status.message} />
        )}
      </Panel>
    </>
  )
}
