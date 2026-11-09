#!/usr/bin/env node
// Generates the TypeScript/Zod and Pydantic code from the OpenAPI contracts (ADR-200, ADR-503).
// `--check` regenerates into a temporary directory and fails when the committed output differs.
import { execFileSync } from 'node:child_process'
import { mkdirSync, mkdtempSync, readdirSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..', '..')
const sharedTypesDir = join(root, 'packages/shared-types')
const tsOutDir = join(sharedTypesDir, 'src/generated')
const pyOutDir = join(root, 'apps/orchestrator/src/apex/contracts/generated')
// The public contract is generated first: openapi-ts empties its output directory, and the internal
// contracts are generated into subdirectories of it.
const specs = [
  { input: 'contracts/openapi.yaml', tsSubdir: '', pyFile: 'models.py' },
  {
    input: 'contracts/internal/browser-worker.openapi.yaml',
    tsSubdir: 'browser-worker',
    pyFile: 'browser_worker.py',
  },
]
const pyHeader = (input) =>
  [
    `# DO NOT EDIT. Generated from ${input} by contracts/scripts/generate.mjs.`,
    '# ruff: noqa: UP035, UP040',
  ].join('\n')

function generateTs(spec, baseDir) {
  const outDir = join(baseDir, spec.tsSubdir)
  mkdirSync(outDir, { recursive: true })
  execFileSync(
    join(sharedTypesDir, 'node_modules/.bin/openapi-ts'),
    ['-f', 'openapi-ts.config.mjs'],
    {
      cwd: sharedTypesDir,
      env: {
        ...process.env,
        APEX_CONTRACTS_TS_OUT: outDir,
        APEX_CONTRACTS_INPUT: join(root, spec.input),
      },
      stdio: 'inherit',
    }
  )
  execFileSync(
    join(root, 'node_modules/.bin/prettier'),
    ['--config', join(root, '.prettierrc'), '--write', outDir],
    { cwd: root, stdio: 'ignore' }
  )
}

function generatePy(spec, outDir) {
  mkdirSync(outDir, { recursive: true })
  execFileSync(
    'uvx',
    [
      '--from',
      'datamodel-code-generator==0.91.0',
      'datamodel-codegen',
      '--input',
      spec.input,
      '--input-file-type',
      'openapi',
      '--output',
      join(outDir, spec.pyFile),
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
      pyHeader(spec.input),
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
      join(outDir, spec.pyFile),
    ],
    { cwd: root, stdio: 'ignore' }
  )
  writeFileSync(join(outDir, '__init__.py'), '')
}

function listFiles(dir, prefix = '') {
  let entries
  try {
    entries = readdirSync(dir, { withFileTypes: true })
  } catch {
    return []
  }
  // Bytecode caches appear after any local test run and are gitignored, so they are not drift.
  return entries
    .filter((entry) => entry.name !== '__pycache__')
    .flatMap((entry) =>
      entry.isDirectory()
        ? listFiles(join(dir, entry.name), join(prefix, entry.name))
        : [join(prefix, entry.name)]
    )
    .sort()
}

function diffDirs(expectedDir, actualDir, label) {
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

function generateAll(tsDir, pyDir) {
  for (const spec of specs) {
    generateTs(spec, tsDir)
    generatePy(spec, pyDir)
  }
}

if (!process.argv.includes('--check')) {
  generateAll(tsOutDir, pyOutDir)
  console.log('contracts: generated TypeScript and Python code')
} else {
  // Inside the repo on purpose: Prettier silently ignores files outside it.
  const tmp = mkdtempSync(join(root, 'contracts', '.check-'))
  try {
    generateAll(join(tmp, 'ts'), join(tmp, 'py'))
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
