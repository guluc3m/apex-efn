import { timingSafeEqual } from 'node:crypto'

const BEARER = /^Bearer (.+)$/

export function isServiceTokenValid(authorization: string | undefined, token: string): boolean {
  const presented = BEARER.exec(authorization ?? '')?.[1]
  if (presented === undefined) {
    return false
  }
  const given = Buffer.from(presented, 'utf8')
  const expected = Buffer.from(token, 'utf8')
  return given.length === expected.length && timingSafeEqual(given, expected)
}
