import { business, decision, health, history, metrics, quarantined } from './data'
import styles from './d.module.css'

/**
 * Direction D — Neumorphism ("soft UI").
 *
 * Surfaces are extruded from a single-tone ground using paired light/dark
 * shadows rather than borders. The known hazard of this style is contrast:
 * shadow-defined edges are invisible to many users, so here the *shapes* are
 * soft while text, figures and status colour stay at full contrast. Interactive
 * elements press inward on :active, which is the one genuinely good idea in
 * this aesthetic — the affordance is physical.
 */
export function DirectionD() {
  return (
    <div className={styles.root}>
      <header className={styles.header}>
        <div className={styles.brand}>
          <span className={styles.mark} aria-hidden="true" />
          <span>Aether</span>
        </div>
        <nav className={styles.nav}>
          <a href="#" className={styles.pillActive}>Receivables</a>
          <a href="#" className={styles.pill}>Approvals</a>
          <a href="#" className={styles.pill}>Activity</a>
        </nav>
        <span className={styles.org}>{business.name}</span>
      </header>

      <main className={styles.main}>
        <div className={styles.titleRow}>
          <div>
            <h1 className={styles.h1}>{business.domainLabel}</h1>
            <p className={styles.sub}>
              Reported {business.reportedAt} · every {business.reportingWindowDays} days
            </p>
          </div>
          <button className={styles.raisedBtn} type="button">Run now</button>
        </div>

        <div className={styles.figures}>
          <div className={styles.figureCard}>
            <span className={styles.figLabel}>At risk each day</span>
            <span className={styles.figValueRisk}>
              ${decision.exposurePerDay.toLocaleString('en-US', { maximumFractionDigits: 0 })}
            </span>
            <span className={styles.figNote}>
              34% of ${decision.arTotal.toLocaleString('en-US')} outstanding
            </span>
          </div>
          <div className={styles.figureCard}>
            <span className={styles.figLabel}>Book health</span>
            <span className={styles.figValue}>{Math.round(health * 100)}%</span>
            <div className={styles.gauge} aria-hidden="true">
              <span style={{ width: `${health * 100}%` }} />
            </div>
          </div>
          <div className={styles.figureCard}>
            <span className={styles.figLabel}>Awaiting you</span>
            <span className={styles.figValueRisk}>1</span>
            <span className={styles.figNote}>{decision.action.toLowerCase()}</span>
          </div>
        </div>

        <section className={styles.panel}>
          <div className={styles.panelHead}>
            <h2 className={styles.panelTitle}>{decision.action}</h2>
            <span className={styles.badge}>{decision.risk}</span>
            <span className={styles.source}>{decision.diagnosisSource}</span>
          </div>
          <div className={styles.inset}>{decision.reason}</div>
          <p className={styles.diagnosis}>{decision.diagnosis.split('\n\n')[0]}</p>
          <div className={styles.actions}>
            <button className={styles.approve} type="button">Approve</button>
            <button className={styles.raisedBtn} type="button">Reject</button>
          </div>
        </section>

        <div className={styles.grid}>
          <section>
            <h3 className={styles.sectionTitle}>Metrics</h3>
            <div className={styles.metricGrid}>
              {metrics.map((m) => (
                <div key={m.key} className={styles.metricCard}>
                  <span className={styles.metricLabel}>{m.label}</span>
                  <span className={m.breached ? styles.metricValueBad : styles.metricValue}>
                    {m.value}
                  </span>
                  <div className={styles.gauge} aria-hidden="true">
                    <span
                      className={m.breached ? styles.gaugeBad : undefined}
                      style={{ width: `${Math.max(4, m.health * 100)}%` }}
                    />
                  </div>
                  <span className={styles.metricHealthy}>Healthy {m.healthy}</span>
                </div>
              ))}
            </div>
          </section>

          <section>
            <h3 className={styles.sectionTitle}>Recent reports</h3>
            <div className={styles.listCard}>
              {history.map((h, i) => (
                <div
                  key={h.date}
                  className={i === 0 ? styles.listRowFirst : styles.listRow}
                >
                  <span>{h.date}</span>
                  <span className={styles.num}>{h.dso}d</span>
                  <span className={styles.num}>{Math.round(h.overdue * 100)}%</span>
                  <span className={styles.num}>{Math.round(h.health * 100)}%</span>
                </div>
              ))}
            </div>

            <div className={styles.rejected}>
              <span className={styles.rejectedHead}>
                Rejected · {quarantined.date} · {quarantined.source}
              </span>
              <p className={styles.rejectedBody}>{quarantined.message}</p>
            </div>
          </section>
        </div>
      </main>
    </div>
  )
}
