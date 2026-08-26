import { business, decision, health, history, metrics, quarantined } from './data'
import styles from './a.module.css'

/**
 * Direction A — "Ledger".
 *
 * A calm financial instrument. Warm paper, one deep-green accent reserved for
 * money, red used only where risk is real. Top navigation rather than the
 * default left sidebar. Numbers set in tabular figures at display size, because
 * in this product the number *is* the content.
 */
export function DirectionA() {
  return (
    <div className={styles.root}>
      <header className={styles.topbar}>
        <div className={styles.brand}>
          <span className={styles.mark} aria-hidden="true" />
          Aether
        </div>
        <nav className={styles.nav}>
          <a className={styles.navItemActive} href="#">Overview</a>
          <a className={styles.navItem} href="#">Approvals <span className={styles.count}>1</span></a>
          <a className={styles.navItem} href="#">Domains</a>
          <a className={styles.navItem} href="#">Activity</a>
        </nav>
        <div className={styles.org}>{business.name}</div>
      </header>

      <main className={styles.main}>
        <div className={styles.lede}>
          <div>
            <p className={styles.eyebrow}>{business.domainLabel}</p>
            <h1 className={styles.h1}>
              Collections have slipped for the third week running.
            </h1>
            <p className={styles.standfirst}>
              Reported {business.reportedAt} · expects a reading every{' '}
              {business.reportingWindowDays} days
            </p>
          </div>
          <div className={styles.exposure}>
            <span className={styles.exposureLabel}>At risk each day</span>
            <span className={styles.exposureValue}>
              ${decision.exposurePerDay.toLocaleString('en-US', { maximumFractionDigits: 0 })}
            </span>
            <span className={styles.exposureNote}>
              34% of ${decision.arTotal.toLocaleString('en-US')} outstanding
            </span>
          </div>
        </div>

        <section className={styles.decision}>
          <div className={styles.decisionMain}>
            <div className={styles.decisionHead}>
              <span className={styles.riskDot} aria-hidden="true" />
              <h2 className={styles.decisionTitle}>{decision.action}</h2>
              <span className={styles.awaiting}>awaiting your decision</span>
            </div>
            <p className={styles.diagnosis}>{decision.diagnosis.split('\n\n')[0]}</p>
            <p className={styles.diagnosis}>{decision.diagnosis.split('\n\n')[1]}</p>
            <div className={styles.actions}>
              <button className={styles.primary} type="button">Approve</button>
              <button className={styles.ghost} type="button">Reject</button>
              <span className={styles.provenance}>{decision.diagnosisSource}</span>
            </div>
          </div>
          <aside className={styles.decisionSide}>
            <dl className={styles.facts}>
              <div><dt>Cost to act</dt><dd>${decision.interventionCost}</dd></div>
              <div><dt>Pays back in</dt><dd>2.5 hours</dd></div>
              <div><dt>Book health</dt><dd>{Math.round(health * 100)}%</dd></div>
            </dl>
          </aside>
        </section>

        <section>
          <h3 className={styles.sectionTitle}>What moved</h3>
          <div className={styles.metrics}>
            {metrics.map((m) => (
              <article key={m.key} className={m.breached ? styles.metricBad : styles.metric}>
                <div className={styles.metricTop}>
                  <span className={styles.metricLabel}>{m.label}</span>
                  <span className={styles.metricValue}>{m.value}</span>
                </div>
                <div className={styles.bar} aria-hidden="true">
                  <span style={{ width: `${Math.max(3, m.health * 100)}%` }} />
                </div>
                <p className={styles.metricNote}>{m.note}</p>
                <p className={styles.metricHealthy}>Healthy {m.healthy}</p>
              </article>
            ))}
          </div>
        </section>

        <section className={styles.twoUp}>
          <div>
            <h3 className={styles.sectionTitle}>Recent reports</h3>
            <table className={styles.table}>
              <thead>
                <tr><th>Week</th><th>DSO</th><th>Overdue</th><th>Health</th></tr>
              </thead>
              <tbody>
                {history.map((h) => (
                  <tr key={h.date}>
                    <td>{h.date}</td>
                    <td className={styles.num}>{h.dso}d</td>
                    <td className={styles.num}>{Math.round(h.overdue * 100)}%</td>
                    <td className={styles.num}>{Math.round(h.health * 100)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div>
            <h3 className={styles.sectionTitle}>Rejected reading</h3>
            <div className={styles.rejected}>
              <p className={styles.rejectedMeta}>
                {quarantined.date} · via {quarantined.source}
              </p>
              <p className={styles.rejectedBody}>{quarantined.message}</p>
              <p className={styles.rejectedNote}>
                Held back from every decision until the feed is corrected.
              </p>
            </div>
          </div>
        </section>
      </main>
    </div>
  )
}
