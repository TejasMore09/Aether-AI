'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'

/**
 * Navigation that shows where you are.
 *
 * The active item is *pressed into* the surface rather than raised out of it —
 * in a neumorphic system that inversion is the state change, and it reads
 * instantly without needing a colour or an underline to carry the meaning.
 */
export function NavLink({ href, children }: { href: string; children: React.ReactNode }) {
  const pathname = usePathname()
  const active = href === '/' ? pathname === '/' : pathname.startsWith(href)

  return (
    <Link
      href={href}
      aria-current={active ? 'page' : undefined}
      className="rounded-[12px] px-[17px] py-[9px] text-sm transition-[box-shadow,color] duration-[240ms] ease-[var(--ease-forge)]"
      style={{
        background: 'var(--color-raised)',
        boxShadow: active ? 'var(--press)' : 'var(--raise-sm)',
        color: active ? 'var(--color-copper)' : 'var(--color-ink-soft)',
        fontWeight: active ? 600 : 500,
      }}
    >
      {children}
    </Link>
  )
}
