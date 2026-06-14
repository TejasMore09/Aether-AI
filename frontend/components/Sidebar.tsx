'use client'
import Link from 'next/link'
import { usePathname } from 'next/navigation'

export default function Sidebar() {
  const pathname = usePathname()
  
  const links = [
    { name: 'Global Dashboard', href: '/', icon: 'dashboard' },
    { name: 'Model Registry', href: '/registry', icon: 'inventory_2' },
    { name: 'Drift & Data Quality', href: '/drift', icon: 'monitoring' },
    { name: 'Adaptive Pipelines', href: '/pipelines', icon: 'account_tree' },
    { name: 'Scenario Simulator', href: '/insights', icon: 'science' },
    { name: 'Meta-Intelligence', href: '/meta', icon: 'psychology_alt' },
    { name: 'AI Explanations', href: '/explain', icon: 'psychology' },
    { name: 'Integrations & Alerts', href: '/integrations', icon: 'hub' },
  ]

  return (
    <nav className="fixed left-0 top-0 h-full w-64 border-r border-zinc-800 bg-zinc-950 flex flex-col z-50">
      <div className="p-6 border-b border-zinc-800 flex items-center gap-3">
        <svg width="28" height="28" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
          <path d="M12 2L2 22H22L12 2Z" stroke="#FAFAFA" strokeWidth="1.5" strokeLinejoin="round"/>
          <path d="M12 8L7 18H17L12 8Z" fill="#FAFAFA" fillOpacity="0.1"/>
          <circle cx="12" cy="8" r="1.5" fill="#FAFAFA"/>
          <circle cx="7" cy="18" r="1.5" fill="#FAFAFA"/>
          <circle cx="17" cy="18" r="1.5" fill="#FAFAFA"/>
        </svg>
        <div>
          <div className="text-lg font-black tracking-tighter text-white uppercase">Aether AI</div>
          <div className="font-sans tracking-tight text-[10px] uppercase font-semibold text-zinc-500 mt-1">Enterprise Engine</div>
        </div>
      </div>
      
      <div className="flex-1 py-4 flex flex-col">
        {links.map(l => {
          const isActive = pathname === l.href || (l.href !== '/' && pathname.startsWith(l.href))
          return (
            <Link key={l.href} href={l.href} className={`flex items-center gap-3 px-4 py-3 transition-colors ${isActive ? 'bg-zinc-900 text-white border-l-2 border-white' : 'text-zinc-500 hover:text-zinc-200 hover:bg-zinc-900 hover:text-white'}`}>
              <span className="material-symbols-outlined" style={isActive ? { fontVariationSettings: "'FILL' 1" } : {}}>{l.icon}</span>
              <span className="font-sans tracking-tight text-sm uppercase font-semibold">{l.name}</span>
            </Link>
          )
        })}
      </div>
      
      <div className="p-6 border-t border-zinc-800">
        <button className="w-full bg-white text-black font-label-caps text-label-caps py-4 uppercase border border-white hover:bg-zinc-200 transition-colors">New Pipeline</button>
      </div>
    </nav>
  )
}
