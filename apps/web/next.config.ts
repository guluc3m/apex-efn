import type { NextConfig } from 'next'
import createNextIntlPlugin from 'next-intl/plugin'

const withNextIntl = createNextIntlPlugin()

const nextConfig: NextConfig = {
  reactStrictMode: true,
  // Standalone output (D1-09): the runtime image runs `node .next/standalone/server.js`
  // instead of `next start`, so it never re-loads next.config.ts at startup and does not
  // need TypeScript (a devDependency) in the production image. See apps/web/Dockerfile.
  output: 'standalone',
  transpilePackages: [
    '@apex/ui',
    '@apex/shared-types',
    '@apex/money',
    '@apex/scoring',
    '@apex/crypto-client',
  ],
  typedRoutes: true,
}

export default withNextIntl(nextConfig)
