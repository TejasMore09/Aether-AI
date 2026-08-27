'use client'

import Link from 'next/link'

import { CountUp, Rise, Stagger } from '@/components/motion'
import { business, decision, health, history, metrics, quarantined } from './data'

import styles from './explore.module.css'

/**
 * The public surface — Minimal.
 *
 * No account, no backend: this is a worked example of one real report, so a
 * stranger can judge whether the product is worth signing up for. Calm and
 * legible rather than dense, because the reader has no context yet and is not
 * operating anything.
 *
 * It is explicitly labelled as an example. A demo that pretends to be live
 * data is a small lie that costs trust the moment someone notices.
 */
export default function ExplorePage() {
  return (
    <div className={styles.root}>
      <header className={styles.header}>
        <span className={styles.brand}>Aether</span>
        <span className={styles.badge}>Worked example · not live data</span>
        <nav className={styles.nav}>
          <Link href="/login" className={styles.navItem}>
            Sign in
          </Link>
          <Link href="/signup" className={styles.navCta}>
            Create an organization
          </Link>
        </nav>
      </header>

      <main className={styles.main}>
        <Stagger>
          <Rise className={styles.lede}>
            <p className={styles.eyebrow}>
              {business.domainLabel} · {business.name} · {business.reportedAt}
            </p>
            <h1 className={styles.h1}>Escalate collections</h1>
            <p className={styles.exposureLine}>
              <span className={styles.exposure}>
                <CountUp to={decision.exposurePerDay} prefix="$" />
              </span>
              <span className={styles.exposureUnit}>at risk each day</span>
            </p>
            <p className={styles.reason}>{decision.reason}</p>
            <p className={styles.gate}>
              Your agent will not act on this by itself. It waits for a person.
            </p>
          </Rise>

          <Rise className={styles.block}>
            <h2 className={styles.blockTitle}>What it found</h2>
            <div className={styles.prose}>
              <p>{decision.diagnosis.split('\n\n')[0]}</p>
              <p>{decision.diagnosis.split('\n\n')[1]}</p>
            </div>
          </Rise>

          <Rise className={styles.block}>
            <h2 className={styles.blockTitle}>This week</h2>
            <dl className={styles.metrics}>
              {metrics.map((m) => (
                <div key={m.key} className={styles.row}>
                  <dt className={styles.rowLabel}>{m.label}</dt>
                  <dd className={m.breached ? styles.rowValueBad : styles.rowValue}>{m.value}</dd>
                  <dd className={styles.rowNote}>healthy {m.healthy}</dd>
                </div>
              ))}
              <div className={styles.row}>
                <dt className={styles.rowLabel}>Book health</dt>
                <dd className={styles.rowValueBad}>{Math.round(health * 100)}%</dd>
                <dd className={styles.rowNote}>88% four weeks ago</dd>
              </div>
            </dl>
          </Rise>

          <Rise className={styles.block}>
            <h2 className={styles.blockTitle}>Trend</h2>
            <dl className={styles.metrics}>
              {history.map((h) => (
                <div key={h.date} className={styles.row}>
                  <dt className={styles.rowLabel}>{h.date}</dt>
                  <dd className={styles.rowValue}>{h.dso}d</dd>
                  <dd className={styles.rowNote}>
                    {Math.round(h.overdue * 100)}% overdue · {Math.round(h.health * 100)}% health
                  </dd>
                </div>
              ))}
            </dl>
          </Rise>

          <Rise className={styles.block}>
            <h2 className={styles.blockTitle}>A reading it refused</h2>
            <div className={styles.prose}>
              <p>
                <span className={styles.rejectedMeta}>
                  {quarantined.date} · {quarantined.source}
                </span>
                <br />
                {quarantined.message} It was held back from this report entirely, rather than
                quietly moving the numbers.
              </p>
            </div>
          </Rise>

          <Rise className={styles.cta}>
            <p className={styles.ctaLine}>
              This is one report for one business function. Your agent watches yours on a
              schedule and only stops you when the money justifies it.
            </p>
            <Link href="/signup" className={styles.ctaButton}>
              Create an organization
            </Link>
          </Rise>
        </Stagger>
      </main>
    </div>
  )
}
