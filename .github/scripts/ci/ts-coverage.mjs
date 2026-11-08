#!/usr/bin/env node
// TypeScript coverage ratchet (D1-04). Run from anywhere; paths are relative to the repository root.
//
//   node .github/scripts/ci/ts-coverage.mjs                  measure and compare with the baseline file
//   node .github/scripts/ci/ts-coverage.mjs --update-baseline  raise baseline values to the measured ones
//   options: --baseline <file>        baseline file to read or write (default .github/coverage-baseline.json)
//            --main-baseline <file>   baseline that main has (default: git show $CI_BASE_REF, else origin/main)
//
// Rules, per package (lines, statements, branches, functions; percentages rounded down to 2 decimals):
//  - all four metrics >= 80, or no baseline entry: hard gate, every metric must be >= 80 ("graduated").
//  - otherwise: every metric must be >= its baseline - 0.01. A metric above its baseline prints a hint.
//  - baselines only go up: fail if the working copy is lower than main's baseline for any value, or if an
//    entry that main has is removed while the package is still below 80.
//  - --update-baseline writes max(working copy, main, measured) for every value. It never lowers a value.
// Vitest runs with no thresholds: all gating happens here, so the rules above are the only rules.

import { spawnSync } from 'node:child_process'
import { mkdtempSync, readFileSync, writeFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '../../..')
const PACKAGE_DIRS = ['packages/money', 'packages/scoring', 'packages/crypto-client']
const METRICS = ['lines', 'statements', 'branches', 'functions']
const HARD_GATE = 80
const DEFAULT_BASELINE = '.github/coverage-baseline.json'

// Integers in hundredths of a percent. Comparing these avoids floating-point surprises at the 0.01 boundary.
const hundredths = (pct) => Math.round(pct * 100)
// Round down to 2 decimals. The epsilon absorbs binary noise such as 71.73 * 100 = 7172.999...
export const floor2 = (pct) => Math.floor(pct * 100 + 1e-7) / 100

export function judge(name, measured, baseline) {
  const problems = []
  const hints = []
  const graduated = METRICS.every((m) => hundredths(measured[m]) >= HARD_GATE * 100)
  const hardGate = !baseline || graduated

  if (hardGate) {
    for (const m of METRICS) {
      if (hundredths(measured[m]) < HARD_GATE * 100) {
        problems.push(`${m} ${measured[m]}% is below the hard ${HARD_GATE}% gate`)
      }
    }
  } else {
    for (const m of METRICS) {
      if (hundredths(measured[m]) < hundredths(baseline[m]) - 1) {
        problems.push(`${m} ${measured[m]}% is below baseline ${baseline[m]}% (allowed drop: 0.01)`)
      }
    }
  }
  if (baseline) {
    for (const m of METRICS) {
      if (hundredths(measured[m]) > hundredths(baseline[m])) {
        hints.push(`${m}: raise baseline to ${floor2(measured[m])}`)
      }
    }
  }
  const status = graduated
    ? 'graduated (hard 80%)'
    : hardGate
      ? 'hard 80% (no baseline)'
      : 'ratchet'
  return { name, status, problems, hints }
}

export function monotonic(name, working, main, measured) {
  if (!main) return []
  if (!working) {
    const stillBelow = METRICS.some((m) => hundredths(measured[m]) < HARD_GATE * 100)
    return stillBelow
      ? [
          `baseline entry removed although main has one and the package is still below ${HARD_GATE}%`,
        ]
      : []
  }
  return METRICS.filter((m) => hundredths(working[m]) < hundredths(main[m])).map(
    (m) => `${m} baseline lowered from ${main[m]} (main) to ${working[m]} (working copy)`
  )
}

function readJson(path) {
  return JSON.parse(readFileSync(path, 'utf8'))
}

function readMainBaseline(ref, explicitPath) {
  if (explicitPath) {
    return { source: explicitPath, data: readJson(explicitPath) }
  }
  const verified = spawnSync('git', ['rev-parse', '--verify', '--quiet', `${ref}^{commit}`], {
    cwd: ROOT,
  })
  if (verified.status !== 0) {
    return { source: null, reason: `ref ${ref} not found; monotonic check skipped` }
  }
  const shown = spawnSync('git', ['show', `${ref}:${DEFAULT_BASELINE}`], {
    cwd: ROOT,
    encoding: 'utf8',
  })
  if (shown.status !== 0) {
    return { source: null, reason: `${ref} has no ${DEFAULT_BASELINE}; monotonic check skipped` }
  }
  return { source: ref, data: JSON.parse(shown.stdout) }
}

function runVitest(name, outDir) {
  const result = spawnSync(
    'pnpm',
    [
      '--filter',
      name,
      'exec',
      'vitest',
      'run',
      '--coverage.enabled',
      '--coverage.provider=v8',
      '--coverage.include=src/**',
      '--coverage.exclude=src/**/*.test.ts',
      '--coverage.reporter=json-summary',
      '--coverage.reporter=text',
      `--coverage.reportsDirectory=${outDir}`,
    ],
    { cwd: ROOT, stdio: 'inherit' }
  )
  return result.status === 0
}

function parseArgs(argv) {
  const opts = { update: false, baseline: join(ROOT, DEFAULT_BASELINE), mainBaseline: null }
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i]
    if (a === '--update-baseline') opts.update = true
    else if (a === '--baseline') opts.baseline = resolve(argv[++i])
    else if (a === '--main-baseline') opts.mainBaseline = resolve(argv[++i])
    else throw new Error(`unknown argument: ${a}`)
  }
  return opts
}

function main() {
  const opts = parseArgs(process.argv.slice(2))
  const names = PACKAGE_DIRS.map((dir) => readJson(join(ROOT, dir, 'package.json')).name)

  const baselineFile = fileExists(opts.baseline) ? readJson(opts.baseline) : {}
  const unknown = Object.keys(baselineFile).filter((k) => k !== '_comment' && !names.includes(k))
  if (unknown.length) {
    console.error(`ERROR: baseline has entries for unknown packages: ${unknown.join(', ')}`)
    process.exit(1)
  }

  const mainRef = process.env.CI_BASE_REF || 'origin/main'
  const mainInfo = readMainBaseline(mainRef, opts.mainBaseline)
  if (!mainInfo.data) console.log(`NOTE: ${mainInfo.reason}`)
  const mainFile = mainInfo.data || null

  const tmp = mkdtempSync(join(tmpdir(), 'apex-ts-coverage-'))
  const failures = []
  const rows = []
  const measuredByName = {}
  try {
    for (const dir of PACKAGE_DIRS) {
      const name = readJson(join(ROOT, dir, 'package.json')).name
      console.log(`::group::coverage ${name}`)
      const outDir = join(tmp, name.replace(/[^a-z0-9-]/gi, '_'))
      if (!runVitest(name, outDir)) failures.push(`${name}: tests failed`)
      console.log('::endgroup::')
      const summaryPath = join(outDir, 'coverage-summary.json')
      if (!fileExists(summaryPath)) {
        failures.push(`${name}: no coverage summary was produced`)
        continue
      }
      const total = readJson(summaryPath).total
      const measured = Object.fromEntries(METRICS.map((m) => [m, total[m].pct]))
      measuredByName[name] = measured
      rows.push({ name, measured })
    }
  } finally {
    rmSync(tmp, { recursive: true, force: true })
  }

  if (opts.update) {
    if (failures.length) {
      failures.forEach((f) => console.error(`FAIL: ${f}`))
      console.error('baseline not written: fix the failures above first')
      process.exit(1)
    }
    const next = {}
    for (const name of names) {
      const entry = {}
      const measured = measuredByName[name]
      if (!measured) {
        if (baselineFile[name]) next[name] = baselineFile[name]
        continue
      }
      for (const m of METRICS) {
        const candidates = [floor2(measured[m])]
        if (baselineFile[name]) candidates.push(baselineFile[name][m])
        if (mainFile?.[name]) candidates.push(mainFile[name][m])
        entry[m] = Math.max(...candidates)
      }
      next[name] = entry
    }
    const out = {
      _comment:
        'TypeScript coverage ratchet. Raise with: node .github/scripts/ci/ts-coverage.mjs --update-baseline',
      ...next,
    }
    writeFileSync(opts.baseline, JSON.stringify(out, null, 2) + '\n')
    console.log(`baseline written: ${opts.baseline}`)
    for (const name of Object.keys(next)) console.log(`  ${name}: ${JSON.stringify(next[name])}`)
    return
  }

  const reports = []
  for (const { name, measured } of rows) {
    const working = baselineFile[name]
    const report = judge(name, measured, working)
    report.problems.push(...monotonic(name, working, mainFile?.[name], measured))
    reports.push(report)
    if (report.problems.length) failures.push(...report.problems.map((p) => `${name}: ${p}`))
  }

  console.log('\nTypeScript coverage ratchet')
  console.log('package                 lines   statements  branches  functions  status')
  for (const { name, measured } of rows) {
    const r = reports.find((x) => x.name === name)
    const cells = METRICS.map((m) => String(measured[m].toFixed(2)).padStart(9)).join(' ')
    console.log(`${name.padEnd(22)} ${cells}  ${r.status}`)
    for (const hint of r.hints) console.log(`  hint: ${name} ${hint}`)
  }
  if (failures.length) {
    console.log('')
    for (const f of failures) console.error(`FAIL: ${f}`)
    process.exit(1)
  }
  console.log('\nTypeScript coverage ratchet passed')
}

function fileExists(path) {
  try {
    readFileSync(path, 'utf8')
    return true
  } catch {
    return false
  }
}

// Run as a script, not when imported by tests.
if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main()
}
