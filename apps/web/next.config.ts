import type { NextConfig } from 'next'
import createNextIntlPlugin from 'next-intl/plugin'

const withNextIntl = createNextIntlPlugin()

const nextConfig: NextConfig = {
  reactStrictMode: true,
  transpilePackages: ['@trato/ui', '@trato/shared-types', '@trato/money', '@trato/scoring', '@trato/crypto-client'],
  experimental: {
    typedRoutes: true,
  },
}

export default withNextIntl(nextConfig)
