import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))

export default {
  input: resolve(here, '../../contracts/openapi.yaml'),
  output: {
    path: process.env.APEX_CONTRACTS_TS_OUT ?? resolve(here, 'src/generated'),
    postProcess: [],
  },
  plugins: [
    { name: '@hey-api/typescript' },
    { name: 'zod', definitions: { types: { infer: true } } },
  ],
}
