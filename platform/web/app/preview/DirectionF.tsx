import { business, decision, health, history, metrics, quarantined } from './data'
import styles from './f.module.css'

/**
 * Direction F — Minimalism.
 *
 * No cards, no shadows, no fills. Structure comes from hairline rules, a strict
 * spacing scale and one weight jump. There is nothing to hide behind here: the
 * type scale and the alignment either work or the page looks broken, which is
 * exactly why it suits a product whose content is a handful of decisive numbers.
 * The only colour in the interface is the one that means money is at risk.
 */
export function DirectionF() {
  return (
    <div className={styles.root}>
      <header className={styles.header}>
        <span className={styles.brand}>Aether</span>
        <nav className={styles.nav}>
          <a href="#" className={styles.navActive}>Receivables</a>
          <a href="#" className={styles.navItem}>Approvals</a>
          <a href="#" className={styles.navItem}>Activity</a>
        </nav>
        <span className={styles.org}>{business.name}</span>
      </header>

      <main className={styles.main}>
        <section className={styles.lede}>
          <p className={styles.eyebrow}>{business.domainLabel} · {business.reportedAt}</p>
          <h1 className={styles.h1}>Escalate collections</h1>
          <p className={styles.exposureLine}>
            <span className={styles.exposure}>
              ${decision.exposurePerDay.toLocaleString('en-US', { maximumFractionDigits: 0 })}
            </span>
            <span className={styles.exposureUnit}>at risk each day</span>
          </p>
          <p className={styles.reason}>{decision.reason}</p>
          <div className={styles.actions}>
            <button className={styles.approve} type="button">Approve</button>
            <button className={styles.reject} type="button">Reject</button>
            <span className={styles.source}>{decision.diagnosisSource}</span>
          </div>
        </section>

        <section className={styles.block}>
          <h2 className={styles.blockTitle}>Finding</h2>
          <div className={styles.prose}>
            <p>{decision.diagnosis.split('\n\n')[0]}</p>
            <p>{decision.diagnosis.split('\n\n')[1]}</p>
          </div>
        </section>

        <section className={styles.block}>
          <h2 className={styles.blockTitle}>This week</h2>
          <dl className={styles.metrics}>
            {metrics.map((m) => (
              <div key={m.key} className={styles.metricRow}>
                <dt className={styles.metricLabel}>{m.label}</dt>
                <dd className={m.breached ? styles.metricValueBad : styles.metricValue}>
                  {m.value}
                </dd>
                <dd className={styles.metricHealthy}>healthy {m.healthy}</dd>
              </div>
            ))}
            <div className={styles.metricRow}>
              <dt className={styles.metricLabel}>Book health</dt>
              <dd className={styles.metricValueBad}>{Math.round(health * 100)}%</dd>
              <dd className={styles.metricHealthy}>88% four weeks ago</dd>
            </div>
          </dl>
        </section>

        <section className={styles.block}>
          <h2 className={styles.blockTitle}>Trend</h2>
          <dl className={styles.metrics}>
            {history.map((h) => (
              <div key={h.date} className={styles.metricRow}>
                <dt className={styles.metricLabel}>{h.date}</dt>
                <dd className={styles.metricValue}>{h.dso}d</dd>
                <dd className={styles.metricHealthy}>
                  {Math.round(h.overdue * 100)}% overdue · {Math.round(h.health * 100)}% health
                </dd>
              </div>
            ))}
          </dl>
        </section>

        <section className={styles.block}>
          <h2 className={styles.blockTitle}>Rejected reading</h2>
          <div className={styles.prose}>
            <p>
              <span className={styles.rejectedMeta}>
                {quarantined.date} · {quarantined.source}
              </span>
              <br />
              {quarantined.message} Held back from this report entirely.
            </p>
          </div>
        </section>
      </main>
    </div>
  )
}
