import type { NextConfig } from 'next'

/**
 * The staff console.
 *
 * A separate application from web/ on purpose. If the console were a route
 * group inside the customer dashboard, that deployment's server code would
 * hold main-brain credentials and one routing mistake would be a
 * cross-boundary mistake. Here, the customer app has no configuration that
 * points at the brain and no code that talks to it.
 */
const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  async headers() {
    return [
      {
        source: '/:path*',
        headers: [
          { key: 'X-Frame-Options', value: 'DENY' },
          { key: 'X-Content-Type-Options', value: 'nosniff' },
          { key: 'Referrer-Policy', value: 'no-referrer' },
          // An internal console has no business being indexed, and staff
          // navigating to a tenant should not leak that id to anything.
          { key: 'X-Robots-Tag', value: 'noindex, nofollow' },
        ],
      },
    ]
  },
}

export default nextConfig
