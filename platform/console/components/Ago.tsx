'use client'

import { useEffect, useState } from 'react'

import { ago, whenUTC } from './instrument'

/**
 * Freshness, without lying to the hydrator.
 *
 * "4m ago" cannot be server-rendered: the server computes it at request time
 * and the client recomputes it a second later, so the two disagree and React
 * discards the difference rather than patching it. Rendering the absolute
 * time first makes both sides agree, and the relative form takes over on
 * mount.
 *
 * It then keeps ticking, which is what an operations console actually wants —
 * you can leave the fleet open and watch an agent go silent, rather than
 * reloading to find out.
 */
export function Ago({ iso }: { iso: string | null }) {
  const [relative, setRelative] = useState<string | null>(null)

  useEffect(() => {
    const tick = () => setRelative(ago(iso))
    tick()
    // 20s is fine: nothing here changes meaning faster than that, and a
    // per-second interval on a few hundred rows is wasted work.
    const id = setInterval(tick, 20_000)
    return () => clearInterval(id)
  }, [iso])

  if (relative !== null) return <>{relative}</>
  return <>{iso ? whenUTC(iso) : 'never'}</>
}
