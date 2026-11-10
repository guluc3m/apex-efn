import { mkdir, writeFile } from 'node:fs/promises'
import path from 'node:path'

export interface ArtifactStore {
  put(key: string, bytes: Uint8Array): Promise<void>
}

export class InMemoryArtifactStore implements ArtifactStore {
  readonly objects = new Map<string, Uint8Array>()

  put(key: string, bytes: Uint8Array): Promise<void> {
    this.objects.set(key, bytes)
    return Promise.resolve()
  }
}

export class FsArtifactStore implements ArtifactStore {
  private readonly baseDir: string

  constructor(baseDir: string) {
    this.baseDir = path.resolve(baseDir)
  }

  async put(key: string, bytes: Uint8Array): Promise<void> {
    const target = this.resolve(key)
    await mkdir(path.dirname(target), { recursive: true })
    await writeFile(target, bytes)
  }

  private resolve(key: string): string {
    if (key.length === 0 || key.includes('..') || path.isAbsolute(key)) {
      throw new Error('invalid artifact key')
    }
    const target = path.resolve(this.baseDir, key)
    if (!target.startsWith(this.baseDir + path.sep)) {
      throw new Error('invalid artifact key')
    }
    return target
  }
}
