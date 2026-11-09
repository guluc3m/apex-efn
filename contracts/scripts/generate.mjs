#!/usr/bin/env node
// Generates the TypeScript/Zod and Pydantic code from contracts/openapi.yaml (ADR-200).
// `--check` regenerates into a temporary directory and fails when the committed output differs.
import { execFileSync } from 'node:child_process'
import { mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..')
const sharedTypesDir = join(root, 'packages/shared-types')
const tsOutDir = join(sharedTypesDir, 'src/generated')
const pyOutDir = join(root, 'apps/orchestrator/src/apex/contracts/generated')
const pyHeader = [
  '# DO NOT EDIT. Generated from contracts/openapi.yaml by contracts/scripts/generate.mjs.',
  '# ruff: noqa: UP035, UP040',
].join('\n')

function generateTs(outDir) {
  mkdirSync(outDir, { recursive: true })
  execFileSync(
    join(sharedTypesDir, 'node_modules/.bin/openapi-ts'),
    ['-f', 'openapi-ts.config.mjs'],
    {
      cwd: sharedTypesDir,
      env: { ...process.env, APEX_CONTRACTS_TS_OUT: outDir },
      stdio: 'inherit',
    }
  )
  execFileSync(
    join(root, 'node_modules/.bin/prettier'),
    ['--config', join(root, '.prettierrc'), '--write', outDir],
    { cwd: root, stdio: 'ignore' }
  )
}

function generatePy(outDir) {
  mkdirSync(outDir, { recursive: true })
  execFileSync(
    'uvx',
    [
      '--from',
      'datamodel-code-generator==0.91.0',
      'datamodel-codegen',
      '--input',
      'contracts/openapi.yaml',
      '--input-file-type',
      'openapi',
      '--output',
      join(outDir, 'models.py'),
      '--output-model-type',
      'pydantic_v2.BaseModel',
      '--target-python-version',
      '3.12',
      '--use-annotated',
      '--use-standard-collections',
      '--use-union-operator',
      '--field-constraints',
      '--use-schema-description',
      '--enum-field-as-literal',
      'one',
      '--disable-timestamp',
      '--use-double-quotes',
      '--custom-file-header',
      pyHeader,
    ],
    {
      cwd: root,
      env: { ...process.env, PYTHONWARNINGS: 'ignore::FutureWarning' },
      stdio: ['ignore', 'inherit', 'inherit'],
    }
  )
  execFileSync(
    'uvx',
    [
      '--from',
      'ruff==0.17.4',
      'ruff',
      'format',
      '--config',
      join(root, 'apps/orchestrator/pyproject.toml'),
      join(outDir, 'models.py'),
    ],
    { cwd: root, stdio: 'ignore' }
  )
  writeFileSync(join(outDir, '__init__.py'), '')
}

function diffDirs(expectedDir, actualDir, label) {
  const listFiles = (dir) => {
    try {
      // Bytecode caches appear after any local test run and are gitignored, so they are not drift.
      return readdirSync(dir)
        .filter((name) => name !== '__pycache__')
        .sort()
    } catch {
      return []
    }
  }
  const expected = listFiles(expectedDir)
  const actual = listFiles(actualDir)
  const names = [...new Set([...expected, ...actual])].sort()
  const problems = []
  for (const name of names) {
    if (!actual.includes(name)) {
      problems.push(`${label}/${name}: missing from the repository`)
    } else if (!expected.includes(name)) {
      problems.push(`${label}/${name}: no longer produced by the contract`)
    } else if (!readFileSync(join(expectedDir, name)).equals(readFileSync(join(actualDir, name)))) {
      problems.push(`${label}/${name}: differs from the contract`)
    }
  }
  return problems
}

if (!process.argv.includes('--check')) {
  generateTs(tsOutDir)
  generatePy(pyOutDir)
  console.log('contracts: generated TypeScript and Python code')
} else {
  // Inside the repo on purpose: Prettier silently ignores files outside it.
  const tmp = mkdtempSync(join(root, 'contracts', '.check-'))
  try {
    generateTs(join(tmp, 'ts'))
    generatePy(join(tmp, 'py'))
    const problems = [
      ...diffDirs(join(tmp, 'ts'), tsOutDir, 'packages/shared-types/src/generated'),
      ...diffDirs(join(tmp, 'py'), pyOutDir, 'apps/orchestrator/src/apex/contracts/generated'),
    ]
    if (problems.length > 0) {
      console.error('contracts: generated code is out of date. Run `pnpm contracts:generate`.')
      for (const problem of problems) console.error(`  - ${problem}`)
      process.exitCode = 1
    } else {
      console.log('contracts: generated code is up to date')
    }
  } finally {
    rmSync(tmp, { recursive: true, force: true })
  }
}
