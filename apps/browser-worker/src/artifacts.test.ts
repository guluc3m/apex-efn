import { mkdtemp, readFile, rm } from 'node:fs/promises'
import os from 'node:os'
import path from 'node:path'

import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { FsArtifactStore } from './artifacts.js'

describe('FsArtifactStore', () => {
  let dir = ''

  beforeEach(async () => {
    dir = await mkdtemp(path.join(os.tmpdir(), 'bw-artifacts-'))
  })

  afterEach(async () => {
    await rm(dir, { recursive: true, force: true })
  })

  it('writes the bytes under the key', async () => {
    const store = new FsArtifactStore(dir)
    const key = 'screenshots/tenant-1/chat-1/shot-1.png'
    await store.put(key, new TextEncoder().encode('PNG'))
    expect(await readFile(path.join(dir, key), 'utf8')).toBe('PNG')
  })

  it.each(['../escape.png', 'screenshots/../../escape.png', '/etc/passwd', ''])(
    'rejects the key %j',
    async (key) => {
      const store = new FsArtifactStore(dir)
      await expect(store.put(key, new Uint8Array([1]))).rejects.toThrow('invalid artifact key')
    }
  )
})
