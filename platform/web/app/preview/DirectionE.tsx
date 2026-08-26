import { business, decision, health, history, metrics, quarantined } from './data'
import styles from './e.module.css'

/**
 * Direction E — Glassmorphism.
 *
 * Frosted panels over an ambient mesh ground. Two things keep it honest:
 * the backdrop is a deep teal/amber mesh rather than the purple-blue gradient
 * that marks most AI-generated glass UI, and every translucent surface has a
 * solid fallback under `prefers-reduced-transparency` — without it the style
 * is unusable for anyone who turns transparency off.
 */
export function DirectionE() {
  return (
    <div className={styles.root}>
      <div className={styles.mesh} aria-hidden="true">
        <span className={styles.blobA} />
        <span className={styles.blobB} />
        <span className={styles.blobC} />
      </div>

      <div className={styles.content}>
        <header className={styles.header}>
          <div className={styles.brand}>
            <span className={styles.mark} aria-hidden="true" />
            Aether
          </div>
          <nav className={styles.nav}>
            <a href="#" className={styles.navActive}>Receivables</a>
            <a href="#" className={styles.navItem}>Approvals</a>
            <a href="#" className={styles.navItem}>Activity</a>
          </nav>
          <span className={styles.org}>{business.name}</span>
        </header>

        <div className={styles.titleRow}>
          <div>
            <p className={styles.eyebrow}>{business.domainLabel}</p>
            <h1 className={styles.h1}>Collections slipped again this week.</h1>
            <p className={styles.sub}>
              Reported {business.reportedAt} · every {business.reportingWindowDays} days
            </p>
          </div>
        </div>

        <div className={styles.figures}>
          <div className={styles.glassStrong}>
            <span className={styles.figLabel}>At risk each day</span>
            <span className={styles.figValueRisk}>
              ${decision.exposurePerDay.toLocaleString('en-US', { maximumFractionDigits: 0 })}
            </span>
            <span className={styles.figNote}>
              34% of ${decision.arTotal.toLocaleString('en-US')} outstanding
            </span>
          </div>
          <div className={styles.glass}>
            <span className={styles.figLabel}>Book health</span>
            <span className={styles.figValue}>{Math.round(health * 100)}%</span>
            <span className={styles.figNote}>88% four weeks ago</span>
          </div>
          <div className={styles.glass}>
            <span className={styles.figLabel}>Awaiting you</span>
            <span className={styles.figValueRisk}>1</span>
            <span className={styles.figNote}>{decision.action.toLowerCase()}</span>
          </div>
        </div>

        <section className={styles.glassPanel}>
          <div className={styles.panelHead}>
            <h2 className={styles.panelTitle}>{decision.action}</h2>
            <span className={styles.badge}>{decision.risk}</span>
            <span className={styles.source}>{decision.diagnosisSource}</span>
          </div>
          <p className={styles.reason}>{decision.reason}</p>
          <p className={styles.diagnosis}>{decision.diagnosis.split('\n\n')[0]}</p>
          <div className={styles.actions}>
            <button className={styles.approve} type="button">Approve</button>
            <button className={styles.reject} type="button">Reject</button>
          </div>
        </section>

        <div className={styles.grid}>
          <section className={styles.glassPanel}>
            <h3 className={styles.sectionTitle}>Metrics</h3>
            <div className={styles.metricList}>
              {metrics.map((m) => (
                <div key={m.key} className={styles.metricRow}>
                  <span className={styles.metricLabel}>{m.label}</span>
                  <span className={styles.track} aria-hidden="true">
                    <span
                      className={m.breached ? styles.fillBad : styles.fill}
                      style={{ width: `${Math.max(4, m.health * 100)}%` }}
                    />
                  </span>
                  <span className={m.breached ? styles.metricValueBad : styles.metricValue}>
                    {m.value}
                  </span>
                </div>
              ))}
            </div>
          </section>

          <section className={styles.glassPanel}>
            <h3 className={styles.sectionTitle}>Recent reports</h3>
            <table className={styles.table}>
              <thead>
                <tr><th>Week</th><th>DSO</th><th>Overdue</th><th>Health</th></tr>
              </thead>
              <tbody>
                {history.map((h) => (
                  <tr key={h.date}>
                    <td>{h.date}</td>
                    <td>{h.dso}d</td>
                    <td>{Math.round(h.overdue * 100)}%</td>
                    <td>{Math.round(h.health * 100)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className={styles.rejected}>
              <span className={styles.rejectedHead}>
                Rejected · {quarantined.date} · {quarantined.source}
              </span>
              <p className={styles.rejectedBody}>{quarantined.message}</p>
            </div>
          </section>
        </div>
      </div>
    </div>
  )
}
