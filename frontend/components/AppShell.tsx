'use client'

import Sidebar from '@/components/Sidebar'
import TopBar from '@/components/TopBar'
import BackendBanner from '@/components/BackendBanner'

export default function AppShell({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', minHeight: '100vh', background: '#0A0A0A' }}>
      <Sidebar />
      <div style={{ marginLeft: '256px', flex: 1, display: 'flex', flexDirection: 'column' }}>
        <TopBar title={title} />
        <BackendBanner />
        <main style={{ flex: 1, padding: '88px 48px 48px', maxWidth: '1600px', width: '100%', margin: '0 auto' }}>
          {children}
        </main>
      </div>
    </div>
  )
}
