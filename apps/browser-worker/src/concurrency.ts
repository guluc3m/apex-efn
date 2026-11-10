const noop = (): void => undefined

/** Runs tasks for the same key one after another. Different keys run concurrently. */
export class KeyedMutex {
  private readonly tails = new Map<string, Promise<void>>()

  run<T>(key: string, task: () => Promise<T>): Promise<T> {
    const previous = this.tails.get(key) ?? Promise.resolve()
    const result = previous.then(task)
    const tail = result.then(noop, noop)
    this.tails.set(key, tail)
    return result.finally(() => {
      if (this.tails.get(key) === tail) {
        this.tails.delete(key)
      }
    })
  }
}

/** Turns a synchronous computation into a promise, so in-memory implementations can keep their promise-based signatures. */
export function settle<T>(compute: () => T): Promise<T> {
  return new Promise<T>((resolve) => {
    resolve(compute())
  })
}
