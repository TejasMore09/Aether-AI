'use client'

import { AnimatePresence } from 'framer-motion'
import { useState } from 'react'

import { business, decision, health, history, metrics, quarantined } from './data'
import { CountUp, Fill, PressButton, Rise, Stagger, motion } from './motion'
import styles from './g.module.css'

/**
 * Direction G — "Forge": neumorphic form, Console's warm charcoal and copper.
 *
 * Dark neumorphism is harder than the light kind: the "light" shadow cannot be
 * white, it has to be a barely-lifted charcoal, or every surface looks like it
 * is glowing. The payoff is that soft extrusion stops feeling like a toy and
 * starts feeling like machined metal, which suits a product about money.
 *
 * Motion is on arrival and on interaction only — nothing loops.
 */
export function DirectionG() {
  const [resolved, setResolved] = useState<null | 'approved' | 'rejected'>(null)

  return (
    <div className={styles.root}>
      <div className={styles.glow} aria-hidden="true" />

      <header className={styles.header}>
        <div className={styles.brand}>
          <span className={styles.mark} aria-hidden="true" />
          <span className={styles.brandName}>Aether</span>
        </div>
        <nav className={styles.nav}>
          {['Overview', 'Receivables', 'Approvals', 'Activity'].map((item) => (
            <a
              key={item}
              href="#"
              className={item === 'Receivables' ? styles.pillActive : styles.pill}
            >
              {item}
            </a>
          ))}
        </nav>
        <div className={styles.orgChip}>
          <span className={styles.orgDot} aria-hidden="true" />
          {business.name}
        </div>
      </header>

      <main className={styles.main}>
        <Stagger className={styles.titleRow}>
          <Rise>
            <p className={styles.eyebrow}>{business.domainLabel}</p>
            <h1 className={styles.h1}>Collections have slipped for a third week.</h1>
            <p className={styles.sub}>
              Reported {business.reportedAt} · reviewed every {business.reportingWindowDays} days
            </p>
          </Rise>
        </Stagger>

        <Stagger className={styles.figures} delay={0.12}>
          <Rise className={styles.figureCard}>
            <span className={styles.figLabel}>At risk each day</span>
            <span className={styles.figValueRisk}>
              <CountUp to={decision.exposurePerDay} prefix="$" />
            </span>
            <span className={styles.figNote}>
              34% of ${decision.arTotal.toLocaleString('en-US')} outstanding
            </span>
          </Rise>

          <Rise className={styles.figureCard}>
            <span className={styles.figLabel}>Book health</span>
            <span className={styles.figValue}>
              <CountUp to={health * 100} format={(n) => `${Math.round(n)}%`} />
            </span>
            <span className={styles.gauge} aria-hidden="true">
              <Fill className={styles.gaugeFillBad} pct={health * 100} delay={0.3} />
            </span>
            <span className={styles.figNote}>88% four weeks ago</span>
          </Rise>

          <Rise className={styles.figureCard}>
            <span className={styles.figLabel}>Awaiting you</span>
            <span className={styles.figValueRisk}>{resolved ? 0 : 1}</span>
            <span className={styles.figNote}>
              {resolved ? `${resolved} just now` : decision.action.toLowerCase()}
            </span>
          </Rise>
        </Stagger>

        <AnimatePresence mode="wait">
          {resolved === null ? (
            <motion.section
              key="decision"
              className={styles.panel}
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -12, scale: 0.99 }}
              transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1], delay: 0.2 }}
            >
              <div className={styles.panelHead}>
                <span className={styles.pulse} aria-hidden="true" />
                <h2 className={styles.panelTitle}>{decision.action}</h2>
                <span className={styles.badge}>{decision.risk}</span>
                <span className={styles.source}>{decision.diagnosisSource}</span>
              </div>

              <div className={styles.inset}>{decision.reason}</div>
              <p className={styles.diagnosis}>{decision.diagnosis.split('\n\n')[0]}</p>

              <div className={styles.actions}>
                <PressButton
                  className={styles.approve}
                  onClick={() => setResolved('approved')}
                >
                  Approve
                </PressButton>
                <PressButton
                  className={styles.reject}
                  onClick={() => setResolved('rejected')}
                >
                  Reject
                </PressButton>
              </div>
            </motion.section>
          ) : (
            <motion.section
              key="resolved"
              className={styles.resolved}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.45, ease: [0.16, 1, 0.3, 1] }}
            >
              <span className={styles.resolvedMark} aria-hidden="true" />
              <div>
                <p className={styles.resolvedTitle}>
                  {decision.action} {resolved}
                </p>
                <p className={styles.resolvedNote}>
                  Recorded in the audit trail against your account. Collections will be
                  chased largest-first from tomorrow morning.
                </p>
              </div>
              <button className={styles.undo} onClick={() => setResolved(null)} type="button">
                Undo
              </button>
            </motion.section>
          )}
        </AnimatePresence>

        <div className={styles.grid}>
          <section>
            <h3 className={styles.sectionTitle}>What moved this week</h3>
            <Stagger className={styles.metricGrid} gap={0.045}>
              {metrics.map((m, i) => (
                <Rise key={m.key} className={styles.metricCard} distance={10}>
                  <span className={styles.metricLabel}>{m.label}</span>
                  <span className={m.breached ? styles.metricValueBad : styles.metricValue}>
                    {m.value}
                  </span>
                  <span className={styles.gauge} aria-hidden="true">
                    <Fill
                      className={m.breached ? styles.gaugeFillBad : styles.gaugeFill}
                      pct={m.health * 100}
                      delay={0.25 + i * 0.04}
                    />
                  </span>
                  <span className={styles.metricNote}>{m.note}</span>
                </Rise>
              ))}
            </Stagger>
          </section>

          <section>
            <h3 className={styles.sectionTitle}>Recent reports</h3>
            <div className={styles.listCard}>
              {history.map((h, i) => (
                <div key={h.date} className={i === 0 ? styles.listRowFirst : styles.listRow}>
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
