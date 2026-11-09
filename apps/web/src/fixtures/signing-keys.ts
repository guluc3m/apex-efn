// //todo_#149: sustituir por GET /v1/keys/me (claves registradas del usuario) cuando exista el BFF
export interface KeyFixture {
  id: string
  device: string
  fingerprint: string
  createdAt: string
  status: 'active' | 'revoked'
}

export const signingKeys: KeyFixture[] = [
  { id: 'key_1', device: 'Portátil · Chrome', fingerprint: 'ed25519:9f3a…41c7', createdAt: '02/11/2026', status: 'active' },
  { id: 'key_2', device: 'Sobremesa · Firefox', fingerprint: 'ed25519:21bd…0e9a', createdAt: '14/06/2026', status: 'revoked' },
]
