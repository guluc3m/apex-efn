import { type NextRequest, NextResponse } from 'next/server'

export const dynamic = 'force-dynamic'

/** `/login` is the public alias for the sign-in entry; Auth.js handles the OAuth dance. */
export function GET(request: NextRequest): Response {
  const target = new URL('/api/auth/signin', request.nextUrl.origin)
  const callbackUrl = request.nextUrl.searchParams.get('callbackUrl')
  if (callbackUrl) target.searchParams.set('callbackUrl', callbackUrl)
  return NextResponse.redirect(target, 307)
}
