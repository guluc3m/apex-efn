import { describe, expect, it } from 'vitest'

import { WorkerError } from '../errors.js'
import { FixedClock } from '../testing/fakes.js'

import { parseRobots, RobotsCache } from './robots.js'

const UA = 'APEX-EFN-bot/0.1 (+https://example.invalid/bot)'
const START = '2026-11-09T10:00:00.000Z'

function allowed(text: string, path: string, userAgent = UA): boolean {
  return parseRobots(text, userAgent).isAllowed(path)
}

describe('parseRobots', () => {
  it('allows everything when there are no rules', () => {
    expect(allowed('', '/anything')).toBe(true)
  })

  it('treats an empty Disallow as allow all', () => {
    expect(allowed('User-agent: *\nDisallow:', '/anything')).toBe(true)
  })

  it('lets a longer Allow override a shorter Disallow (RFC 9309 example)', () => {
    const text = 'User-agent: *\nDisallow: /\nAllow: /public/'
    expect(allowed(text, '/public/page')).toBe(true)
    expect(allowed(text, '/private')).toBe(false)
  })

  it('lets the longest matching rule win in either direction', () => {
    const text = 'User-agent: *\nAllow: /folder\nDisallow: /folder/private'
    expect(allowed(text, '/folder/private/x')).toBe(false)
    expect(allowed(text, '/folder/x')).toBe(true)
  })

  it('lets Allow win a tie of equal length', () => {
    const text = 'User-agent: *\nDisallow: /folder\nAllow: /folder'
    expect(allowed(text, '/folder/x')).toBe(true)
  })

  it('supports the * wildcard inside a path', () => {
    const text = 'User-agent: *\nDisallow: /*.php'
    expect(allowed(text, '/a/b.php?x=1')).toBe(false)
    expect(allowed(text, '/a.html')).toBe(true)
  })

  it('supports the $ end anchor', () => {
    const text = 'User-agent: *\nDisallow: /*.php$'
    expect(allowed(text, '/a.php')).toBe(false)
    expect(allowed(text, '/a.php?x=1')).toBe(true)
    expect(allowed(text, '/a.phpx')).toBe(true)
  })

  it('compares the longest pattern including wildcards', () => {
    const text = 'User-agent: *\nAllow: /page\nDisallow: /*.htm'
    expect(allowed(text, '/page.htm')).toBe(false)
    expect(allowed(text, '/page')).toBe(true)
  })

  it('matches query strings as part of the path', () => {
    const text = 'User-agent: *\nDisallow: /*?q='
    expect(allowed(text, '/search?q=steel')).toBe(false)
    expect(allowed(text, '/search?page=2')).toBe(true)
  })

  it('uses the group that names our token and ignores * for it', () => {
    const text = 'User-agent: APEX-EFN-bot\nDisallow: /x\n\nUser-agent: *\nDisallow: /y'
    expect(allowed(text, '/x')).toBe(false)
    expect(allowed(text, '/y')).toBe(true)
  })

  it('falls back to the * group for other crawlers', () => {
    const text = 'User-agent: APEX-EFN-bot\nDisallow: /x\n\nUser-agent: *\nDisallow: /y'
    expect(allowed(text, '/x', 'OtherBot/1.0')).toBe(true)
    expect(allowed(text, '/y', 'OtherBot/1.0')).toBe(false)
  })

  it('matches the product token case-insensitively', () => {
    expect(allowed('User-agent: apex-efn-BOT\nDisallow: /x', '/x')).toBe(false)
  })

  it('merges consecutive user-agent lines into one group', () => {
    const text = 'User-agent: other\nUser-agent: APEX-EFN-bot\nDisallow: /z'
    expect(allowed(text, '/z')).toBe(false)
  })

  it('starts a new group after a user-agent line that follows rules', () => {
    const text = 'User-agent: other\nDisallow: /z\nUser-agent: APEX-EFN-bot\nDisallow: /w'
    expect(allowed(text, '/z')).toBe(true)
    expect(allowed(text, '/w')).toBe(false)
  })

  it('ignores comments, Sitemap lines, unknown fields and CRLF line endings', () => {
    const text = [
      '# comment line',
      'Sitemap: https://example.invalid/sitemap.xml',
      'User-agent: *',
      'Crawl-delay: 10',
      'Disallow: /private # trailing comment',
      '',
    ].join('\r\n')
    expect(allowed(text, '/private/x')).toBe(false)
    expect(allowed(text, '/public')).toBe(true)
  })

  it('matches the mock marketplace policy: everything except /__control/', () => {
    const text = 'User-agent: *\nAllow: /\nDisallow: /__control/'
    expect(allowed(text, '/products/offer-1')).toBe(true)
    expect(allowed(text, '/__control/reset')).toBe(false)
  })
})

describe('RobotsCache', () => {
  const ROBOTS = 'User-agent: *\nDisallow: /private'
  const PRODUCT = 'https://mock.example.invalid/products/offer-1'

  function cacheWith(
    fetchText: (url: string) => Promise<{ status: number; body: string }>,
    clock: FixedClock,
    ttlMs = 60_000
  ): RobotsCache {
    return new RobotsCache(fetchText, clock, ttlMs)
  }

  it('allows a permitted URL and rejects a disallowed one with robots_disallowed', async () => {
    const cache = cacheWith(
      () => Promise.resolve({ status: 200, body: ROBOTS }),
      new FixedClock(START)
    )
    await expect(cache.assertAllowed(PRODUCT, UA)).resolves.toBeUndefined()
    const error = await cache
      .assertAllowed('https://mock.example.invalid/private/x', UA)
      .catch((caught: unknown) => caught)
    expect(error).toBeInstanceOf(WorkerError)
    expect(error).toMatchObject({ code: 'robots_disallowed', status: 403, retryable: false })
  })

  it('fetches robots.txt once per origin within the TTL, and again after it', async () => {
    const clock = new FixedClock(START)
    const fetched: string[] = []
    const cache = cacheWith((url) => {
      fetched.push(url)
      return Promise.resolve({ status: 200, body: ROBOTS })
    }, clock)
    await cache.assertAllowed(PRODUCT, UA)
    await cache.assertAllowed('https://mock.example.invalid/products/offer-2', UA)
    expect(fetched).toEqual(['https://mock.example.invalid/robots.txt'])
    clock.advance(59_999)
    await cache.assertAllowed(PRODUCT, UA)
    expect(fetched).toHaveLength(1)
    clock.advance(1)
    await cache.assertAllowed(PRODUCT, UA)
    expect(fetched).toHaveLength(2)
  })

  it('allows everything when robots.txt answers 404', async () => {
    const cache = cacheWith(
      () => Promise.resolve({ status: 404, body: 'not found' }),
      new FixedClock(START)
    )
    await expect(
      cache.assertAllowed('https://mock.example.invalid/private/x', UA)
    ).resolves.toBeUndefined()
  })

  it('disallows the whole origin for the TTL when robots.txt answers 500', async () => {
    const clock = new FixedClock(START)
    let calls = 0
    const cache = cacheWith(() => {
      calls += 1
      return Promise.resolve({ status: 500, body: '' })
    }, clock)
    await expect(cache.assertAllowed(PRODUCT, UA)).rejects.toMatchObject({
      code: 'robots_disallowed',
    })
    await expect(cache.assertAllowed('https://mock.example.invalid/', UA)).rejects.toMatchObject({
      code: 'robots_disallowed',
    })
    expect(calls).toBe(1)
  })

  it('disallows the whole origin when robots.txt cannot be reached', async () => {
    const cache = cacheWith(
      () => Promise.reject(new Error('socket hang up')),
      new FixedClock(START)
    )
    await expect(cache.assertAllowed(PRODUCT, UA)).rejects.toMatchObject({
      code: 'robots_disallowed',
    })
  })

  it('matches the query string of the target URL', async () => {
    const cache = cacheWith(
      () => Promise.resolve({ status: 200, body: 'User-agent: *\nDisallow: /*?q=' }),
      new FixedClock(START)
    )
    await expect(
      cache.assertAllowed('https://mock.example.invalid/search?q=steel', UA)
    ).rejects.toMatchObject({
      code: 'robots_disallowed',
    })
    await expect(
      cache.assertAllowed('https://mock.example.invalid/search?page=2', UA)
    ).resolves.toBeUndefined()
  })
})
