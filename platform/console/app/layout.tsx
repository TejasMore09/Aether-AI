import type { Metadata } from 'next'
import { Toaster } from 'sonner'

import './globals.css'

export const metadata: Metadata = {
  title: 'Aether Console',
  description: 'Platform staff console.',
  robots: { index: false, follow: false },
}

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        {children}
        <Toaster
          theme="dark"
          position="bottom-right"
          toastOptions={{
            style: {
              background: 'var(--steel-800)',
              border: '1px solid var(--line)',
              color: 'var(--ink)',
              borderRadius: '4px',
            },
          }}
        />
      </body>
    </html>
  )
}
