'use client'

import { useState } from 'react'

import { DirectionA } from './DirectionA'
import { DirectionB } from './DirectionB'
import { DirectionC } from './DirectionC'
import { DirectionD } from './DirectionD'
import { DirectionE } from './DirectionE'
import { DirectionF } from './DirectionF'
import { DirectionG } from './DirectionG'
import styles from './switcher.module.css'

/**
 * Design preview — three directions for the same page, same data.
 *
 * Mock data only: this route makes no API calls and reads no tenant data.
 * It exists so a visual direction can be chosen against real content rather
 * than described in prose. Delete once the direction is settled.
 */

const DIRECTIONS = [
  {
    key: 'a',
    name: 'Ledger',
    blurb: 'Calm financial instrument · light · one green accent · top nav',
    typeface: 'Geist',
  },
  {
    key: 'b',
    name: 'Console',
    blurb: 'Dark done properly · warm charcoal · copper accent · dense',
    typeface: 'Outfit + JetBrains Mono',
  },
  {
    key: 'c',
    name: 'Brief',
    blurb: 'The report as a document · serif display · figures in the margin',
    typeface: 'Fraunces + Geist',
  },
  {
    key: 'd',
    name: 'Neumorphic',
    blurb: 'Soft extruded UI · one ground tone · depth from paired shadows',
    typeface: 'Manrope',
  },
  {
    key: 'e',
    name: 'Glass',
    blurb: 'Frosted panels over an ambient teal mesh · solid fallback included',
    typeface: 'Sora',
  },
  {
    key: 'g',
    name: 'Forge ★',
    blurb: 'Neumorphic form · Console charcoal + copper · animated',
    typeface: 'Manrope + JetBrains Mono',
  },
  {
    key: 'f',
    name: 'Minimal',
    blurb: 'No cards, no shadows · hairlines and whitespace · colour means risk',
    typeface: 'Instrument Sans',
  },
] as const

export default function PreviewPage() {
  const [active, setActive] = useState<'a' | 'b' | 'c' | 'd' | 'e' | 'f' | 'g'>('g')
  const current = DIRECTIONS.find((d) => d.key === active)!

  return (
    <>
      <div className={styles.bar}>
        <span className={styles.title}>Design directions</span>
        <div className={styles.tabs} role="tablist" aria-label="Design directions">
          {DIRECTIONS.map((d) => (
            <button
              key={d.key}
              role="tab"
              aria-selected={active === d.key}
              className={active === d.key ? styles.tabActive : styles.tab}
              onClick={() => setActive(d.key)}
              type="button"
            >
              <span className={styles.tabName}>{d.name}</span>
            </button>
          ))}
        </div>
        <span className={styles.meta}>
          {current.blurb} · <span className={styles.type}>{current.typeface}</span>
        </span>
      </div>

      <div className={styles.stage}>
        {active === 'a' ? <DirectionA /> : null}
        {active === 'b' ? <DirectionB /> : null}
        {active === 'c' ? <DirectionC /> : null}
        {active === 'd' ? <DirectionD /> : null}
        {active === 'e' ? <DirectionE /> : null}
        {active === 'f' ? <DirectionF /> : null}
        {active === 'g' ? <DirectionG /> : null}
      </div>
    </>
  )
}
