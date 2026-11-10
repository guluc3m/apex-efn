/** One known-answer case. `config` is the engine config slice the case runs with, when the engine has one. */
export interface Vector {
  name: string
  input: unknown
  config?: unknown
  expected: unknown
  /** Absolute tolerance for numbers in `expected`. Overrides the file tolerance. Money is always exact (0). */
  tolerance?: number
}

/** A case where the engine must fail with `expected.error`, the stable error code both languages raise. */
export interface ErrorVector {
  name: string
  input: unknown
  config?: unknown
  expected: { error: string }
}

export interface VectorFile {
  /** Path relative to `packages/test-vectors/`, for test names. */
  file: string
  engine: string
  description: string
  tolerance: number
  vectors: Vector[]
  errors: ErrorVector[]
}

/** Loads every `*.json` under `packages/test-vectors/<folder>/` (recursively, sorted by path). */
export function loadVectorFiles(folder: string): VectorFile[]

/** Compares JSON-like values. Returns `null` on a match, or a description of the first difference. */
export function mismatch(actual: unknown, expected: unknown, tolerance?: number): string | null
