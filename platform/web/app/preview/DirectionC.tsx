import { business, decision, health, history, metrics, quarantined } from './data'
import styles from './c.module.css'

/**
 * Direction C — "Brief".
 *
 * Treats each report as a written briefing rather than a dashboard: a serif
 * display face, an asymmetric two-column measure, and the agent's finding as a
 * lede paragraph. The numbers sit in the margin the way figures sit beside a
 * column of print. The aesthetic risk here is deliberate.
 */
export function DirectionC() {
  return (
    <div className={styles.root}>
      <header className={styles.masthead}>
        <span className={styles.brand}>Aether</span>
        <span className={styles.issue}>
          {business.name} · Report {business.reportedAt}
        </span>
        <nav className={styles.nav}>
          <a href="#" className={styles.navActive}>Receivables</a>
          <a href="#" className={styles.navItem}>Activity</a>
          <a href="#" className={styles.navItem}>Settings</a>
        </nav>
      </header>

      <main className={styles.sheet}>
        <div className={styles.headline}>
          <p className={styles.kicker}>{decision.risk} · awaiting your decision</p>
          <h1 className={styles.h1}>
            Eleven accounts are carrying the whole slip.
          </h1>
        </div>

        <div className={styles.columns}>
          <article className={styles.article}>
            <p className={styles.lede}>{decision.diagnosis.split('\n\n')[0]}</p>
            <p className={styles.body}>{decision.diagnosis.split('\n\n')[1]}</p>

            <div className={styles.recommend}>
              <p className={styles.recommendLabel}>Recommended</p>
              <p className={styles.recommendAction}>{decision.action}</p>
              <p className={styles.recommendReason}>{decision.reason}</p>
              <div className={styles.actions}>
                <button className={styles.approve} type="button">Approve</button>
                <button className={styles.reject} type="button">Reject</button>
              </div>
            </div>

            <h2 className={styles.subhead}>Rejected reading</h2>
            <p className={styles.body}>
              <span className={styles.rejectedMeta}>
                {quarantined.date}, via {quarantined.source}.
              </span>{' '}
              {quarantined.message} It was held back from this report entirely.
            </p>
          </article>

          <aside className={styles.margin}>
            <div className={styles.figure}>
              <span className={styles.figureLabel}>At risk each day</span>
              <span className={styles.figureValue}>
                ${decision.exposurePerDay.toLocaleString('en-US', { maximumFractionDigits: 0 })}
              </span>
              <span className={styles.figureNote}>
                34% of ${decision.arTotal.toLocaleString('en-US')} outstanding
              </span>
            </div>

            <div className={styles.figureSmall}>
              <span className={styles.figureLabel}>Book health</span>
              <span className={styles.figureValueSm}>{Math.round(health * 100)}%</span>
              <span className={styles.figureNote}>88% four weeks ago</span>
            </div>

            <table className={styles.metrics}>
              <caption className={styles.caption}>This week</caption>
              <tbody>
                {metrics.map((m) => (
                  <tr key={m.key} className={m.breached ? styles.rowBad : undefined}>
                    <th scope="row">{m.label}</th>
                    <td>{m.value}</td>
                  </tr>
                ))}
              </tbody>
            </table>

            <table className={styles.metrics}>
              <caption className={styles.caption}>Trend</caption>
              <tbody>
                {history.map((h) => (
                  <tr key={h.date}>
                    <th scope="row">{h.date}</th>
                    <td>{h.dso}d · {Math.round(h.overdue * 100)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </aside>
        </div>
      </main>
    </div>
  )
}
