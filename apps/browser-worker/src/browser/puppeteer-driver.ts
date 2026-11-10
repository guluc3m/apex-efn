/**
 * Puppeteer implementation of the pool's driver (D5-02).
 *
 * Chrome is launched with the stealth plugin and a small set of flags that matter in containers: no `/dev/shm`
 * (it is 64 MB in Docker and Chrome crashes without it), no sandbox (the worker runs as an unprivileged user in
 * a container, not as root on a host) and no GPU. A proxy, when the account has one, is passed as a launch flag so
 * it applies before any request exists.
 *
 * Memory is the resident size of the Chrome process, which is what the container limit counts. `puppeteer-extra`
 * returns a normal `Browser`, so the pool sees the same port as in the tests.
 */

import { randomUUID } from 'node:crypto'
import { readFileSync } from 'node:fs'

import puppeteer from 'puppeteer-extra'
import StealthPlugin from 'puppeteer-extra-plugin-stealth'

import type { BrowserDriver, BrowserHandle, BrowserPage, LaunchOptions } from './driver.js'

export interface PuppeteerDriverOptions {
  headless?: boolean
  executablePath?: string
  /** Extra Chrome flags, appended after the defaults. */
  args?: readonly string[]
  /** Launch timeout in milliseconds. */
  timeoutMs?: number
}

const DEFAULT_ARGS = ['--disable-dev-shm-usage', '--no-sandbox', '--disable-gpu'] as const

puppeteer.use(StealthPlugin())

/**
 * Resident memory of the Chrome process, read from `/proc` on Linux (the production target).
 *
 * It measures the browser process, not its renderer children, so it is a trend rather than an exact container
 * accounting: the memory limit should be set with headroom. On a platform without `/proc` it returns `null`, and
 * the pool then recycles on pages served alone.
 */
function browserRssMb(pid: number | undefined): number | null {
  if (pid === undefined) {
    return null
  }
  try {
    const status = readFileSync(`/proc/${pid}/status`, 'utf8')
    const match = /VmRSS:\s+(\d+) kB/.exec(status)
    const kb = match?.[1]
    return kb === undefined ? null : Math.round(Number(kb) / 1024)
  } catch {
    return null
  }
}

export function createPuppeteerDriver(options: PuppeteerDriverOptions = {}): BrowserDriver {
  return {
    async launch(launch: LaunchOptions): Promise<BrowserHandle> {
      const args = [...DEFAULT_ARGS, ...(options.args ?? [])]
      if (launch.proxyUrl !== null) {
        args.push(`--proxy-server=${launch.proxyUrl}`)
      }
      const browser = await puppeteer.launch({
        headless: options.headless ?? true,
        args,
        ...(options.executablePath === undefined ? {} : { executablePath: options.executablePath }),
        ...(options.timeoutMs === undefined ? {} : { timeout: options.timeoutMs }),
      })
      const browserId = `chrome-${randomUUID()}`
      let pages = 0
      return {
        id: browserId,
        async newPage(): Promise<BrowserPage> {
          const page = await browser.newPage()
          pages += 1
          const pageId = `${browserId}:page-${pages}`
          return {
            id: pageId,
            async close(): Promise<void> {
              await page.close()
            },
          }
        },
        async close(): Promise<void> {
          await browser.close()
        },
        memoryMb(): number | null {
          return browserRssMb(browser.process()?.pid)
        },
        isConnected(): boolean {
          return browser.connected
        },
      }
    },
  }
}
