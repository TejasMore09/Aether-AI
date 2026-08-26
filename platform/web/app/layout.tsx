import type { Metadata } from 'next'
import { JetBrains_Mono, Manrope } from 'next/font/google'

import { Toaster } from '@/components/ui/sonner'

import './globals.css'

/**
 * Fonts are self-hosted through next/font and exposed as CSS variables that
 * globals.css binds to --font-display and --font-mono.
 *
 * Manrope carries the interface: geometric, slightly rounded, and it holds up
 * at the heavy weights the figures need. JetBrains Mono is reserved for
 * machine output — the engine's reasoning line — so that text reads as
 * something the system computed rather than something a person wrote.
 */

const manrope = Manrope({
  subsets: ['latin'],
  weight: ['400', '500', '600', '700', '800'],
  variable: '--font-manrope',
  display: 'swap',
})

const jetbrains = JetBrains_Mono({
  subsets: ['latin'],
  weight: ['400', '500'],
  variable: '--font-jetbrains',
  display: 'swap',
})

export const metadata: Metadata = {
  title: 'Aether',
  description: 'Autonomous operations monitoring for your business.',
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    // `dark` is set permanently: Forge is a single, deliberate surface. There
    // is no light theme to keep in sync, and no flash of the wrong one.
    <html lang="en" className={`dark ${manrope.variable} ${jetbrains.variable}`}>
      <body>
        {children}
        <Toaster
          position="bottom-right"
          toastOptions={{
            style: {
              background: 'var(--color-raised)',
              color: 'var(--color-ink)',
              border: 'none',
              boxShadow: 'var(--raise)',
              borderRadius: '14px',
              fontFamily: 'var(--font-display)',
            },
          }}
        />
      </body>
    </html>
  )
}
