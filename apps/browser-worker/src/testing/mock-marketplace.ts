/**
 * Test harness for the mock marketplace. Record and live tests start it as a subprocess on a free port. Recorded
 * fixtures always use the logical origin `http://mock-a.test`, so replay needs no process and no port.
 */
import { spawn, type ChildProcess } from 'node:child_process'
import net from 'node:net'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import type { HttpRequest, HttpResponse, HttpTransport } from '../adapters/http.js'

export const MOCK_MARKETPLACE_ROOT = fileURLToPath(
  new URL('../../../mock-marketplace/', import.meta.url)
)
export const MOCK_A_FIXTURE_DIR = fileURLToPath(new URL('../../fixtures/mock-a/', import.meta.url))
export const MOCK_A_LOGICAL_ORIGIN = 'http://mock-a.test'

const HEALTH_TIMEOUT_MS = 30_000
const HEALTH_POLL_MS = 200
const STOP_GRACE_MS = 5000

/** Sends requests for `from` to `to` instead. The request URL the inner transport sees is the rewritten one. */
export function rewriteOrigin(inner: HttpTransport, from: string, to: string): HttpTransport {
  return {
    request(req: HttpRequest): Promise<HttpResponse> {
      const url = req.url.startsWith(from) ? `${to}${req.url.slice(from.length)}` : req.url
      return inner.request({ ...req, url })
    },
  }
}

function freePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const server = net.createServer()
    server.once('error', reject)
    server.listen(0, '127.0.0.1', () => {
      const address = server.address()
      server.close(() => {
        if (address === null || typeof address === 'string') {
          reject(new Error('could not reserve a free port'))
          return
        }
        resolve(address.port)
      })
    })
  })
}

async function waitUntilHealthy(origin: string, child: ChildProcess): Promise<void> {
  const deadline = Date.now() + HEALTH_TIMEOUT_MS
  for (;;) {
    if (child.exitCode !== null) {
      throw new Error(`mock marketplace exited with code ${child.exitCode} before it was healthy`)
    }
    try {
      const response = await fetch(`${origin}/healthz`)
      if (response.ok) {
        return
      }
    } catch {
      // Not listening yet. Retry until the deadline.
    }
    if (Date.now() > deadline) {
      throw new Error(`mock marketplace was not healthy within ${HEALTH_TIMEOUT_MS} ms`)
    }
    await new Promise((resolve) => {
      setTimeout(resolve, HEALTH_POLL_MS)
    })
  }
}

export interface RunningMockMarketplace {
  /** Origin of the running process, for example `http://127.0.0.1:41234`. */
  readonly origin: string
  stop(): Promise<void>
}

/**
 * Starts the mock with the fixed seed 7 on a free loopback port and waits for `/healthz`. The process runs in its own
 * group, so `stop` also ends the tsx child that spawns the server.
 */
export async function startMockMarketplace(seed = 7): Promise<RunningMockMarketplace> {
  const port = await freePort()
  const origin = `http://127.0.0.1:${port}`
  const child = spawn(path.join(MOCK_MARKETPLACE_ROOT, 'node_modules/.bin/tsx'), ['src/index.ts'], {
    cwd: MOCK_MARKETPLACE_ROOT,
    env: {
      ...process.env,
      PORT: String(port),
      HOST: '127.0.0.1',
      MOCK_MARKETPLACE_SEED: String(seed),
    },
    stdio: 'ignore',
    detached: true,
  })
  try {
    await waitUntilHealthy(origin, child)
  } catch (error) {
    await stopGroup(child)
    throw error
  }
  return { origin, stop: () => stopGroup(child) }
}

function stopGroup(child: ChildProcess): Promise<void> {
  if (child.exitCode !== null || child.signalCode !== null || child.pid === undefined) {
    return Promise.resolve()
  }
  const pid = child.pid
  return new Promise((resolve) => {
    const force = setTimeout(() => {
      process.kill(-pid, 'SIGKILL')
    }, STOP_GRACE_MS)
    child.once('exit', () => {
      clearTimeout(force)
      resolve()
    })
    process.kill(-pid, 'SIGTERM')
  })
}
