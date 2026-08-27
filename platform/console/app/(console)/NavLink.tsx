'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'

export function NavLink({ href, children }: { href: string; children: React.ReactNode }) {
  const pathname = usePathname()
  const active = href === '/' ? pathname === '/' : pathname.startsWith(href)

  return (
    <Link
      href={href}
      aria-current={active ? 'page' : undefined}
      className="rounded-[4px] border px-[10px] py-[5px] text-[12.5px] transition-colors duration-150"
      style={{
        borderColor: active ? 'var(--steel-600)' : 'transparent',
        background: active ? 'var(--steel-800)' : 'transparent',
        color: active ? 'var(--ink)' : 'var(--ink-faint)',
      }}
    >
      {children}
    </Link>
  )
}
