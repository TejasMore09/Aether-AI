'use client'

import { animate, motion, useInView, useMotionValue, useReducedMotion } from 'framer-motion'
import { useEffect, useRef, useState } from 'react'

/**
 * Shared motion primitives.
 *
 * Two rules keep this from reading as decoration. First, motion happens on
 * arrival and on interaction — never on a loop, because ambient looping
 * animation is the clearest tell of a generated interface. Second, every
 * primitive collapses to a static render under prefers-reduced-motion rather
 * than merely running faster.
 */

// Expo-out: fast departure, long settle. Reads as physical rather than linear.
export const EASE = [0.16, 1, 0.3, 1] as const
export const SPRING = { type: 'spring', stiffness: 420, damping: 32, mass: 0.8 } as const


/**
 * Whether animation can actually run right now.
 *
 * requestAnimationFrame is paused in a background tab, so an animation started
 * there never ticks — a figure animating 0 → $3,875 would sit frozen at $0.
 * For a number that states how much money is at risk, that is not a cosmetic
 * failure, it is a wrong answer. So: animate only when we can, and otherwise
 * render the truth immediately.
 */
function useCanAnimate(): boolean {
  const reduced = useReducedMotion()
  const [visible, setVisible] = useState(
    () => typeof document === 'undefined' || !document.hidden,
  )

  useEffect(() => {
    const onChange = () => setVisible(!document.hidden)
    document.addEventListener('visibilitychange', onChange)
    return () => document.removeEventListener('visibilitychange', onChange)
  }, [])

  return !reduced && visible
}

/** Container that staggers its children in as they arrive. */
export function Stagger({
  children,
  delay = 0,
  gap = 0.055,
  className,
  style,
}: {
  children: React.ReactNode
  delay?: number
  gap?: number
  className?: string
  style?: React.CSSProperties
}) {
  const reduced = useReducedMotion()
  return (
    <motion.div
      className={className}
      style={style}
      initial={reduced ? false : 'hidden'}
      animate="shown"
      variants={{
        hidden: {},
        shown: { transition: { staggerChildren: gap, delayChildren: delay } },
      }}
    >
      {children}
    </motion.div>
  )
}

/** A single item inside a Stagger — rises and fades into place once. */
export function Rise({
  children,
  className,
  style,
  distance = 14,
}: {
  children: React.ReactNode
  className?: string
  style?: React.CSSProperties
  distance?: number
}) {
  const reduced = useReducedMotion()
  if (reduced) {
    return (
      <div className={className} style={style}>
        {children}
      </div>
    )
  }
  return (
    <motion.div
      className={className}
      style={style}
      variants={{
        hidden: { opacity: 0, y: distance },
        shown: { opacity: 1, y: 0, transition: { duration: 0.55, ease: EASE } },
      }}
    >
      {children}
    </motion.div>
  )
}

/**
 * Counts a figure up on arrival.
 *
 * Used only on the number the decision turns on. Applied to every figure it
 * becomes noise; applied to one, it puts the eye where the money is.
 */
export function CountUp({
  to,
  prefix = '',
  duration = 1.1,
  whenInView = false,
  format = (n: number) => Math.round(n).toLocaleString('en-US'),
}: {
  to: number
  prefix?: string
  duration?: number
  /** Gate on scroll position. Only for content below the fold — never for a
   *  figure that is visible on load. */
  whenInView?: boolean
  format?: (n: number) => string
}) {
  const canAnimate = useCanAnimate()
  const ref = useRef<HTMLSpanElement>(null)
  const inView = useInView(ref, { once: true, amount: 0.5 })
  const value = useMotionValue(0)
  const [display, setDisplay] = useState(() => format(to))

  const shouldRun = canAnimate && (whenInView ? inView : true)

  useEffect(() => {
    if (!shouldRun) {
      setDisplay(format(to)) // cannot animate → state the real figure
      return
    }
    value.set(0)
    setDisplay(format(0))
    const controls = animate(value, to, {
      duration,
      ease: EASE,
      onUpdate: (v) => setDisplay(format(v)),
    })
    return () => {
      controls.stop()
      setDisplay(format(to))
    }
  }, [shouldRun, to, duration, value, format])

  return (
    <span ref={ref}>
      {prefix}
      {display}
    </span>
  )
}

/** A bar that fills from zero to its value once it is on screen. */
export function Fill({
  pct,
  className,
}: {
  pct: number
  className?: string
  /** Accepted for call-site symmetry; fills deliberately do not stagger. */
  delay?: number
}) {
  const canAnimate = useCanAnimate()
  const width = `${Math.max(3, Math.min(100, pct))}%`

  // The width is always the real value. Only a transform animates, with no
  // fill-mode and no delay, so the resting style *is* the correct state: if
  // the animation never plays — backgrounded tab, throttled timers, reduced
  // motion — the bar is simply drawn at its true length instead of empty.
  return (
    <span
      className={className}
      style={{
        width,
        transformOrigin: 'left',
        animation: canAnimate ? 'aether-fill-in 850ms cubic-bezier(0.16, 1, 0.3, 1)' : undefined,
      }}
    />
  )
}

/** Button that physically depresses. The affordance is the point. */
export function PressButton({
  children,
  className,
  onClick,
  type = 'button',
}: {
  children: React.ReactNode
  className?: string
  onClick?: () => void
  type?: 'button' | 'submit'
}) {
  const reduced = !useCanAnimate()
  return (
    <motion.button
      type={type}
      className={className}
      onClick={onClick}
      whileHover={reduced ? undefined : { y: -1 }}
      whileTap={reduced ? undefined : { y: 1, scale: 0.985 }}
      transition={SPRING}
    >
      {children}
    </motion.button>
  )
}

export { motion }
