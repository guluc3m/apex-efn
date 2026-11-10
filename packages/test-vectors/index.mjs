// Loader and comparator for the shared domain vectors (ADR-300). Python mirror: apps/orchestrator/tests/domain/vectors.py.
// The JSON schema is enforced on the Python side (schema.json); this loader only checks what a TS runner relies on.
import { readdirSync, readFileSync } from 'node:fs'
import { join, relative } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = fileURLToPath(new URL('.', import.meta.url))

function listJson(dir) {
  return readdirSync(dir, { withFileTypes: true })
    .flatMap((entry) => {
      const path = join(dir, entry.name)
      if (entry.isDirectory()) return listJson(path)
      return entry.name.endsWith('.json') ? [path] : []
    })
    .sort()
}

// JSON.parse silently rounds integers beyond 2^53. Vectors must write those as decimal strings.
function rejectUnsafeIntegers(value, where) {
  if (typeof value === 'number' && Number.isInteger(value) && !Number.isSafeInteger(value)) {
    throw new Error(`${where}: integer ${value} is beyond 2^53, write it as a decimal string`)
  }
  if (value && typeof value === 'object') {
    for (const [key, child] of Object.entries(value)) rejectUnsafeIntegers(child, `${where}.${key}`)
  }
}

export function loadVectorFiles(folder) {
  if (folder === 'signing' || folder.startsWith('signing/')) {
    throw new Error('signing/ has its own format and runners (DEV-2, D2-06)')
  }
  const files = listJson(join(ROOT, folder))
  if (files.length === 0) throw new Error(`no vector files under ${folder}/`)
  return files.map((path) => {
    const file = relative(ROOT, path)
    const data = JSON.parse(readFileSync(path, 'utf8'))
    rejectUnsafeIntegers(data, file)
    if (typeof data.engine !== 'string' || !Array.isArray(data.vectors)) {
      throw new Error(`${file}: needs "engine" and "vectors" (see schema.json)`)
    }
    const errors = data.errors ?? []
    const names = [...data.vectors, ...errors].map((v) => v.name)
    const duplicate = names.find((name, i) => names.indexOf(name) !== i)
    if (duplicate) throw new Error(`${file}: duplicate vector name "${duplicate}"`)
    return {
      file,
      engine: data.engine,
      description: data.description,
      tolerance: data.tolerance ?? 0,
      vectors: data.vectors,
      errors,
    }
  })
}

export function mismatch(actual, expected, tolerance = 0, path = '$') {
  if (typeof expected === 'number' && typeof actual === 'number') {
    return Math.abs(actual - expected) <= tolerance
      ? null
      : `${path}: ${actual} != ${expected} (tolerance ${tolerance})`
  }
  if (Array.isArray(expected)) {
    if (!Array.isArray(actual) || actual.length !== expected.length)
      return `${path}: expected an array of ${expected.length}`
    for (let i = 0; i < expected.length; i++) {
      const diff = mismatch(actual[i], expected[i], tolerance, `${path}[${i}]`)
      if (diff) return diff
    }
    return null
  }
  if (expected !== null && typeof expected === 'object') {
    if (actual === null || typeof actual !== 'object' || Array.isArray(actual))
      return `${path}: expected an object`
    const keys = new Set([...Object.keys(expected), ...Object.keys(actual)])
    for (const key of [...keys].sort()) {
      if (!(key in actual)) return `${path}.${key}: missing`
      if (!(key in expected)) return `${path}.${key}: unexpected`
      const diff = mismatch(actual[key], expected[key], tolerance, `${path}.${key}`)
      if (diff) return diff
    }
    return null
  }
  return actual === expected
    ? null
    : `${path}: ${JSON.stringify(actual)} != ${JSON.stringify(expected)}`
}
