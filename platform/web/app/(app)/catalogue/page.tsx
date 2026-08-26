import Link from 'next/link'

import { api, type DomainPack } from '@/lib/api'
import { EmptyState, ErrorNote, PageHeader } from '@/components/ui'

export default async function CataloguePage() {
  const catalogue = await api.runtime<DomainPack[]>('/v1/catalogue')

  if (!catalogue.ok) {
    return (
      <>
        <PageHeader title="Catalogue" />
        <ErrorNote message={catalogue.message} />
      </>
    )
  }

  return (
    <>
      <PageHeader
        title="Catalogue"
        subtitle="Business functions your agent knows how to watch, and exactly what each one expects."
      />

      {catalogue.data.length === 0 ? (
        <EmptyState
          title="No packs installed"
          body="A pack defines the metrics, healthy ranges and actions for one business function."
        />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
          {catalogue.data.map((pack) => (
            <article key={pack.key} className="card" style={{ padding: 0 }}>
              <div
                style={{
                  padding: '18px 22px',
                  borderBottom: '1px solid var(--color-line)',
                  display: 'flex',
                  justifyContent: 'space-between',
                  gap: 20,
                  flexWrap: 'wrap',
                  alignItems: 'baseline',
                }}
              >
                <div>
                  <h2 style={{ fontSize: 17, fontWeight: 600 }}>{pack.label}</h2>
                  <p
                    style={{
                      fontSize: 13,
                      color: 'var(--color-ink-muted)',
                      margin: '6px 0 0',
                      maxWidth: '68ch',
                    }}
                  >
                    {pack.summary}
                  </p>
                </div>
                <div style={{ textAlign: 'right' }}>
                  <div className="mono" style={{ fontSize: 11, color: 'var(--color-ink-faint)' }}>
                    v{pack.version}
                  </div>
                  <Link
                    href={`/domains/${pack.key}`}
                    className="mono"
                    style={{ fontSize: 11, color: 'var(--color-accent)' }}
                  >
                    OPEN →
                  </Link>
                </div>
              </div>

              <div style={{ padding: '16px 22px', borderBottom: '1px solid var(--color-line)' }}>
                <div className="label" style={{ marginBottom: 10 }}>
                  Metrics it expects
                </div>
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 13 }}>
                    <tbody>
                      {pack.metrics.map((metric) => {
                        const [min, max] = metric.healthy_range
                        const healthy =
                          max !== null && max !== undefined
                            ? `below ${max}`
                            : min !== null && min !== undefined
                              ? `above ${min}`
                              : 'context only'
                        return (
                          <tr key={metric.key}>
                            <td style={{ padding: '7px 0', width: 220 }}>
                              <span className="mono" style={{ fontSize: 12 }}>
                                {metric.key}
                              </span>
                              {metric.required ? (
                                <span
                                  className="mono"
                                  style={{
                                    fontSize: 9,
                                    marginLeft: 8,
                                    color: 'var(--color-risk-high)',
                                  }}
                                >
                                  REQUIRED
                                </span>
                              ) : null}
                            </td>
                            <td
                              style={{
                                padding: '7px 12px',
                                color: 'var(--color-ink-muted)',
                              }}
                            >
                              {metric.label}
                            </td>
                            <td
                              className="mono"
                              style={{
                                padding: '7px 0',
                                fontSize: 11,
                                color: 'var(--color-ink-faint)',
                                whiteSpace: 'nowrap',
                              }}
                            >
                              {healthy}
                            </td>
                          </tr>
                        )
                      })}
                    </tbody>
                  </table>
                </div>
              </div>

              <div style={{ padding: '16px 22px' }}>
                <div className="label" style={{ marginBottom: 10 }}>
                  What it can decide
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
                  {pack.actions.map((action) => (
                    <div key={action.slot} style={{ display: 'flex', gap: 12 }}>
                      <span
                        className="mono"
                        style={{
                          fontSize: 11,
                          fontWeight: 600,
                          minWidth: 170,
                          color: 'var(--color-ink)',
                        }}
                      >
                        {action.label}
                      </span>
                      <span style={{ fontSize: 12.5, color: 'var(--color-ink-muted)' }}>
                        {action.description}
                      </span>
                    </div>
                  ))}
                </div>
              </div>
            </article>
          ))}
        </div>
      )}
    </>
  )
}
