import type { NextConfig } from 'next'

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // A self-contained server bundle with only the modules actually
  // imported, so the image carries neither node_modules nor the source.
  // Without it the runtime stage has to ship the whole dependency tree.
  output: 'standalone',
  // The API base URLs are server-only on purpose: the browser never talks to
  // the platform APIs directly, so no NEXT_PUBLIC_* leak of internal hosts.
  poweredByHeader: false,
  async headers() {
    return [
      {
        source: '/:path*',
        headers: [
          { key: 'X-Frame-Options', value: 'DENY' },
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
        ],
      },
    ]
  },
}

export default nextConfig
