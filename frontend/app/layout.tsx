import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'Self-Evolving AI | Executive Control',
  description: 'Enterprise adaptive AI monitoring and governance platform for C-suite leadership.',
}

import Sidebar from '@/components/Sidebar'
import TopBar from '@/components/TopBar'

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <head>
        <link href="https://fonts.googleapis.com" rel="preconnect"/>
        <link crossOrigin="anonymous" href="https://fonts.gstatic.com" rel="preconnect"/>
        <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Geist+Mono:wght@400;500;600&display=swap" rel="stylesheet"/>
        <link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap" rel="stylesheet"/>
      </head>
      <body suppressHydrationWarning className="bg-background text-on-background flex min-h-screen font-body-base">
        <Sidebar />
        <div className="ml-64 w-[calc(100%-16rem)] min-h-screen relative flex flex-col bg-background">
          <TopBar />
          {children}
        </div>
      </body>
    </html>
  )
}
