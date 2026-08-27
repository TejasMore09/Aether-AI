import Link from 'next/link'

import {
  Bezel,
  EmptyState,
  ErrorNote,
  Eyebrow,
  PageTitle,
  Panel,
  SectionTitle,
} from '@/components/forge'
import { api, type DomainPack } from '@/lib/api'

export default async function CataloguePage() {
  const catalogue = await api.runtime<DomainPack[]>('/v1/catalogue')

  if (!catalogue.ok) {
    return (
      <>
        <PageTitle title="Catalogue" />
        <ErrorNote message={catalogue.message} />
      </>
    )
  }

  return (
    <>
      <div className="mb-5">
        <Eyebrow>Business functions</Eyebrow>
      </div>

      <PageTitle
        title="Catalogue"
        lede="What your agent knows how to watch, the readings each function expects, and the actions it can decide on. Adding a function is a configuration file, never a rebuild."
      />

      {catalogue.data.length === 0 ? (
        <EmptyState
          title="No packs installed"
          body="A pack defines the metrics, healthy ranges and actions for one business function."
        />
      ) : (
        <div className="flex flex-col gap-6">
          {catalogue.data.map((pack) => (
            <Panel key={pack.key} className="!p-0">
              <div className="flex flex-wrap items-start justify-between gap-5 px-7 pb-5 pt-6">
                <div>
                  <h2 className="text-[19px] font-bold tracking-[-0.02em]">{pack.label}</h2>
                  <p
                    className="mt-2 max-w-[66ch] text-[13.5px]"
                    style={{ color: 'var(--color-ink-soft)' }}
                  >
                    {pack.summary}
                  </p>
                </div>
                <Link
                  href={`/domains/${pack.key}`}
                  className="rounded-[12px] px-4 py-2 text-[13px] font-semibold transition-[box-shadow,color] duration-200 ease-[var(--ease-forge)] active:shadow-[var(--press)]"
                  style={{
                    background: 'var(--color-raised)',
                    boxShadow: 'var(--raise-sm)',
                    color: 'var(--color-copper)',
                  }}
                >
                  Open
                </Link>
              </div>

              <div className="grid gap-6 px-7 pb-7 lg:grid-cols-[1.3fr_1fr]">
                <div>
                  <SectionTitle>Readings it expects</SectionTitle>
                  <Bezel radius={16} pad={4}>
                    <div className="px-4 py-2">
                      {pack.metrics.map((metric) => {
                        const [min, max] = metric.healthy_range
                        const healthy =
                          max !== null && max !== undefined
                            ? `below ${max}`
                            : min !== null && min !== undefined
                              ? `above ${min}`
                              : 'context only'
                        return (
                          <div
                            key={metric.key}
                            className="flex flex-wrap items-baseline justify-between gap-3 py-[9px]"
                            title={metric.description}
                          >
                            <span className="text-[13.5px]">
                              {metric.label}
                              {metric.required ? (
                                <span
                                  className="ml-2 text-[10px] font-bold"
                                  style={{ color: 'var(--color-risk)' }}
                                >
                                  REQUIRED
                                </span>
                              ) : null}
                            </span>
                            <span
                              className="tnum text-[12px]"
                              style={{ color: 'var(--color-ink-faint)' }}
                            >
                              {healthy}
                            </span>
                          </div>
                        )
                      })}
                    </div>
                  </Bezel>
                </div>

                <div>
                  <SectionTitle>What it can decide</SectionTitle>
                  <div className="flex flex-col gap-3">
                    {pack.actions.map((action) => (
                      <div key={action.slot}>
                        <p className="text-[13px] font-semibold" style={{ color: 'var(--color-copper)' }}>
                          {action.label.replace(/_/g, ' ').toLowerCase()}
                        </p>
                        <p
                          className="mt-1 text-[12.5px] leading-[1.55]"
                          style={{ color: 'var(--color-ink-soft)' }}
                        >
                          {action.description}
                        </p>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            </Panel>
          ))}
        </div>
      )}
    </>
  )
}
