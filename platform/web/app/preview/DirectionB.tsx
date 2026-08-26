import { business, decision, health, history, metrics, quarantined } from './data'
import styles from './b.module.css'

/**
 * Direction B — "Console".
 *
 * Stays dark, but replaces the generic near-black + neon look: a warm charcoal
 * ground, one desaturated copper accent, and a real display face. Density is
 * kept high because this is an operator surface, but the type carries hierarchy
 * instead of uppercase mono labels doing all the work.
 */
export function DirectionB() {
  return (
    <div className={styles.root}>
      <aside className={styles.rail}>
        <div className={styles.brand}>
          <span className={styles.mark} aria-hidden="true" />
        </div>
        {['Overview', 'Approvals', 'Domains', 'Activity', 'Usage'].map((item, i) => (
          <a
            key={item}
            href="#"
            className={i === 2 ? styles.railItemActive : styles.railItem}
            title={item}
          >
            {item.slice(0, 2)}
          </a>
        ))}
      </aside>

      <div className={styles.body}>
        <header className={styles.head}>
          <div>
            <p className={styles.crumb}>{business.name} / {business.domain}</p>
            <h1 className={styles.h1}>{business.domainLabel}</h1>
          </div>
          <div className={styles.headRight}>
            <span className={styles.stamp}>Reported {business.reportedAt}</span>
            <button className={styles.run} type="button">Run now</button>
          </div>
        </header>

        <div className={styles.hero}>
          <div className={styles.heroFigure}>
            <span className={styles.heroLabel}>Exposure</span>
            <span className={styles.heroValue}>
              ${decision.exposurePerDay.toLocaleString('en-US', { maximumFractionDigits: 0 })}
              <span className={styles.heroUnit}>/day</span>
            </span>
            <span className={styles.heroNote}>
              34% of ${decision.arTotal.toLocaleString('en-US')} outstanding
            </span>
          </div>
          <div className={styles.heroDivider} aria-hidden="true" />
          <div className={styles.heroFigure}>
            <span className={styles.heroLabel}>Book health</span>
            <span className={styles.heroValueMuted}>{Math.round(health * 100)}%</span>
            <span className={styles.heroNote}>down from 88% four weeks ago</span>
          </div>
          <div className={styles.heroDivider} aria-hidden="true" />
          <div className={styles.heroFigure}>
            <span className={styles.heroLabel}>Awaiting you</span>
            <span className={styles.heroValueAlert}>1</span>
            <span className={styles.heroNote}>{decision.action.toLowerCase()}</span>
          </div>
        </div>

        <section className={styles.panel}>
          <div className={styles.panelHead}>
            <h2 className={styles.panelTitle}>{decision.action}</h2>
            <span className={styles.risk}>{decision.risk}</span>
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
          <section>
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
                  <span className={styles.metricHealthy}>{m.healthy}</span>
                </div>
              ))}
            </div>
          </section>

          <section>
            <h3 className={styles.sectionTitle}>Reports</h3>
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
              <p className={styles.rejectedHead}>
                Rejected · {quarantined.date} · {quarantined.source}
              </p>
              <p className={styles.rejectedBody}>{quarantined.message}</p>
            </div>
          </section>
        </div>
      </div>
    </div>
  )
}
