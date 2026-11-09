// Regenerates jcs-numbers.json: `node packages/test-vectors/signing/generate-numbers.mjs`.
// Expected strings come from the JavaScript engine's own Number::toString, which RFC 8785 adopts. The sample is
// seeded, so the output only changes when this script does.
import { writeFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const here = new URL('.', import.meta.url)

// RFC 8785 Appendix B, copied from the RFC text.
const appendixB = [
  ['0000000000000000', '0', 'zero'],
  ['8000000000000000', '0', 'minus zero'],
  ['0000000000000001', '5e-324', 'min positive number'],
  ['8000000000000001', '-5e-324', 'min negative number'],
  ['7fefffffffffffff', '1.7976931348623157e+308', 'max positive number'],
  ['ffefffffffffffff', '-1.7976931348623157e+308', 'max negative number'],
  ['4340000000000000', '9007199254740992', 'max positive integer'],
  ['c340000000000000', '-9007199254740992', 'max negative integer'],
  ['4430000000000000', '295147905179352830000', '~2**68'],
  ['44b52d02c7e14af5', '9.999999999999997e+22', ''],
  ['44b52d02c7e14af6', '1e+23', ''],
  ['44b52d02c7e14af7', '1.0000000000000001e+23', ''],
  ['444b1ae4d6e2ef4e', '999999999999999700000', ''],
  ['444b1ae4d6e2ef4f', '999999999999999900000', ''],
  ['444b1ae4d6e2ef50', '1e+21', ''],
  ['3eb0c6f7a0b5ed8c', '9.999999999999997e-7', ''],
  ['3eb0c6f7a0b5ed8d', '0.000001', ''],
  ['41b3de4355555553', '333333333.3333332', ''],
  ['41b3de4355555554', '333333333.33333325', ''],
  ['41b3de4355555555', '333333333.3333333', ''],
  ['41b3de4355555556', '333333333.3333334', ''],
  ['41b3de4355555557', '333333333.33333343', ''],
  ['becbf647612f3696', '-0.0000033333333333333333', ''],
  ['43143ff3c1cb0959', '1424953923781206.2', 'round to even'],
]

const invalid = [
  ['7fffffffffffffff', 'NaN'],
  ['7ff8000000000000', 'quiet NaN'],
  ['7ff0000000000000', 'Infinity'],
  ['fff0000000000000', '-Infinity'],
]

const view = new DataView(new ArrayBuffer(8))
const fromHex = (hex) => {
  view.setBigUint64(0, BigInt(`0x${hex}`))
  return view.getFloat64(0)
}
const toHex = (value) => {
  view.setFloat64(0, value)
  return view.getBigUint64(0).toString(16).padStart(16, '0')
}

// xorshift64*, seeded: uniform bit patterns cover every exponent; scaled decimals cover everyday amounts.
let state = 0x9e3779b97f4a7c15n
const next = () => {
  state ^= state >> 12n
  state ^= (state << 25n) & 0xffffffffffffffffn
  state ^= state >> 27n
  return (state * 0x2545f4914f6cdd1dn) & 0xffffffffffffffffn
}

const sample = new Map()
while (sample.size < 1200) {
  const value = fromHex(next().toString(16).padStart(16, '0'))
  if (Number.isFinite(value)) sample.set(toHex(value), value)
}
while (sample.size < 2000) {
  const digits = Number(next() % 10n ** BigInt(1 + Number(next() % 17n)))
  const value = (Number(next() % 2n) ? -1 : 1) * (digits / 10 ** Number(next() % 12n))
  sample.set(toHex(value), value)
}

for (const [hex, expected] of appendixB) {
  if (String(fromHex(hex)) !== expected && !(expected === '0' && Object.is(fromHex(hex), -0))) {
    throw new Error(`this engine disagrees with RFC 8785 Appendix B for ${hex}`)
  }
}

const vectors = [
  ...appendixB.map(([hex, canonical, comment]) => ({
    name: `rfc8785 appendix B ${hex}${comment ? ` (${comment})` : ''}`,
    input: { ieee754: hex },
    expected: { canonical },
  })),
  ...[...sample].map(([hex, value]) => ({
    name: `sample ${hex}`,
    input: { ieee754: hex },
    expected: { canonical: String(value) },
  })),
]

const description =
  'RFC 8785 number serialization (ECMAScript Number::toString). `input.ieee754` is the big-endian hex of an IEEE 754 double. `errors` (NaN, infinities) must be rejected.'
const source =
  'RFC 8785 Appendix B, plus a seeded sample serialized by the JavaScript engine (Node.js 22). Regenerate with generate-numbers.mjs.'
const errors = invalid.map(([hex, name]) => ({
  name,
  input: { ieee754: hex },
  expected: { error: 'not_finite' },
}))

// Formatted with the repository's Prettier config, so the file is identical to what a commit hook would write.
const target = fileURLToPath(new URL('jcs-numbers.json', here))
const prettier = await import('prettier')
const text = JSON.stringify({ description, source, vectors, errors })
writeFileSync(
  target,
  await prettier.format(text, { ...(await prettier.resolveConfig(target)), filepath: target })
)
console.log(`${vectors.length} number vectors`)
