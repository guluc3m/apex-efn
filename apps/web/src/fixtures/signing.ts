// //todo_#150: sustituir por la sesión de firma real (GET /v1/signing-sessions). Sin sesión: nunca se simula una activa.
export const signingSession: { expiresAt: string | undefined; signer: string; signaturesLeft: number } = {
  expiresAt: undefined,
  signer: 'Marta Ruiz',
  signaturesLeft: 0,
}
