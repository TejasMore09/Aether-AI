import { Fraunces, Geist, JetBrains_Mono, Outfit } from 'next/font/google'

/**
 * Fonts are loaded with next/font, which self-hosts them and emits a CSS
 * variable per family. The old globals.css named 'Inter' and 'Geist Mono'
 * without ever loading either, so the app silently rendered in system
 * fallbacks — that is the single biggest reason it read as unstyled.
 */

const geist = Geist({
  subsets: ['latin'],
  variable: '--font-geist',
  display: 'swap',
})

const outfit = Outfit({
  subsets: ['latin'],
  weight: ['400', '500', '600'],
  variable: '--font-outfit',
  display: 'swap',
})

const fraunces = Fraunces({
  subsets: ['latin'],
  weight: ['600', '700'],
  variable: '--font-fraunces',
  display: 'swap',
})

const jetbrains = JetBrains_Mono({
  subsets: ['latin'],
  weight: ['400', '500'],
  variable: '--font-jetbrains',
  display: 'swap',
})

export default function PreviewLayout({ children }: { children: React.ReactNode }) {
  return (
    <div
      className={`${geist.variable} ${outfit.variable} ${fraunces.variable} ${jetbrains.variable}`}
    >
      {children}
    </div>
  )
}
