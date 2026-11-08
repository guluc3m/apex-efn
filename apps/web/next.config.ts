import type { NextConfig } from 'next'
import createNextIntlPlugin from 'next-intl/plugin'

const withNextIntl = createNextIntlPlugin()

const nextConfig: NextConfig = {
  reactStrictMode: true,
  transpilePackages: ['@apex/ui', '@apex/shared-types', '@apex/money', '@apex/scoring', '@apex/crypto-client'],
  typedRoutes: true,
}

export default withNextIntl(nextConfig)
