import { ErrorNote, Eyebrow, PageTitle, Panel, SectionTitle } from '@/components/forge'
import { api, type ApiKeyRow, type DomainPack } from '@/lib/api'
import { readSession } from '@/lib/session'

import { KeyManager } from './KeyManager'
import { Snippet } from './Snippet'

export const metadata = { title: 'Connections · Aether' }

const RUNTIME_URL = process.env.AETHER_PUBLIC_RUNTIME_URL ?? 'http://localhost:8200'

export default async function ConnectionsPage() {
  const session = await readSession()
  const [keys, packs] = await Promise.all([
    api.control<ApiKeyRow[]>('/v1/api-keys'),
    // /v1/catalogue is the pack *definitions*; /v1/domains is this tenant's
    // inventory and carries no metric schema.
    api.runtime<DomainPack[]>('/v1/catalogue'),
  ])

  if (!keys.ok) {
    return (
      <>
        <PageTitle title="Connections" />
        <ErrorNote message={keys.message} />
      </>
    )
  }

  const canManage = session?.role === 'owner'
  const live = keys.data.filter((k) => !k.revoked).length

  // Build the example against a domain this organization actually has, with
  // its real metric keys. A generic snippet would have to be translated before
  // it worked, and translation is where integrations go wrong.
  const pack = packs.ok ? packs.data[0] : undefined
  const domainKey = pack?.key ?? 'receivables'
  const sampleMetrics = (pack?.metrics ?? [])
    .filter((m) => m.required)
    .slice(0, 4)
    .map((m) => {
      const [low, high] = m.healthy_range
      const mid = low !== null && high !== null ? (low + high) / 2 : (low ?? high ?? 1)
      return `      "${m.key}": ${Number(mid.toFixed(2))}`
    })

  const body = sampleMetrics.length
    ? `{\n    "source": "nightly-sync",\n    "metrics": {\n${sampleMetrics.join(',\n')}\n    }\n  }`
    : `{ "source": "nightly-sync", "metrics": {} }`

  const curl = [
    `curl -X POST ${RUNTIME_URL}/v1/domains/${domainKey}/readings \\`,
    `  -H "X-API-Key: $AETHER_KEY" \\`,
    `  -H "Content-Type: application/json" \\`,
    `  -d '${body}'`,
  ].join('\n')

  return (
    <>
      <div className="mb-5">
        <Eyebrow>
          {live === 0
            ? 'Nothing is connected yet'
            : `${live} key${live === 1 ? '' : 's'} in service`}
        </Eyebrow>
      </div>

      <PageTitle
        title="Connections"
        lede="Keys let a system push readings on its own schedule, with nobody signed in. A key can add data and nothing else — it cannot approve a decision, read your audit trail, or see a diagnosis."
      />

      <section className="mb-11">
        <SectionTitle>Ingest keys</SectionTitle>
        <KeyManager keys={keys.data} canManage={canManage} />
        {!canManage && (
          <p className="mt-4 text-[12.5px]" style={{ color: 'var(--color-ink-faint)' }}>
            Issuing and revoking keys is restricted to owners. A key outlives every session,
            so minting one is a different act from using the product.
          </p>
        )}
      </section>

      <section>
        <SectionTitle>Pushing a reading</SectionTitle>
        <Panel>
          <p
            className="mb-5 max-w-[68ch] text-[13.5px] leading-relaxed"
            style={{ color: 'var(--color-ink-soft)' }}
          >
            Send the metrics your {pack?.label.toLowerCase() ?? domainKey} pack defines. Every
            reading passes the quality gate first: a contradictory or implausible one is
            quarantined rather than dropped, so you can see what arrived and why it was held
            back.
          </p>
          <Snippet code={curl} label="the example request" />
          <dl className="mt-6 grid gap-x-8 gap-y-4 sm:grid-cols-2">
            <Fact
              term="Authentication"
              detail="X-API-Key, on every request. There is no session and no refresh to manage."
            />
            <Fact
              term="On success"
              detail="201 with the gate's verdict — whether the reading was accepted, and any issues it raised."
            />
            <Fact
              term="If a key leaks"
              detail="Revoke it here. The next request using it is refused; nothing already ingested is affected."
            />
            <Fact
              term="Scope"
              detail="A key belongs to this organization alone and cannot reach another one, by database policy rather than by application code."
            />
          </dl>
        </Panel>
      </section>
    </>
  )
}

function Fact({ term, detail }: { term: string; detail: string }) {
  return (
    <div>
      <dt
        className="text-[11px] font-semibold uppercase tracking-[0.14em]"
        style={{ color: 'var(--color-ink-faint)' }}
      >
        {term}
      </dt>
      <dd className="mt-[6px] text-[13.5px] leading-relaxed">{detail}</dd>
    </div>
  )
}
