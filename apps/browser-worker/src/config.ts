/**
 * Browser worker configuration
 */

export const config = {
  redisUrl: process.env.REDIS_URL ?? 'redis://localhost:6379',
  scrapingConcurrency: parseInt(process.env.SCRAPING_CONCURRENCY ?? '3', 10),
  negotiationConcurrency: parseInt(process.env.NEGOTIATION_CONCURRENCY ?? '2', 10),
  proxyUrl: process.env.PROXY_URL,
  browserPoolSize: parseInt(process.env.BROWSER_POOL_SIZE ?? '5', 10),
  maxPagesPerBrowser: parseInt(process.env.MAX_PAGES_PER_BROWSER ?? '50', 10),
}
