import { proxyToOrchestrator } from '@/server/bff/proxy'

// Streaming responses and per-request auth: never cache or prerender.
export const dynamic = 'force-dynamic'
export const runtime = 'nodejs'

type Context = { params: Promise<{ path: string[] }> }

async function handle(request: Request, { params }: Context): Promise<Response> {
  const { path } = await params
  return proxyToOrchestrator(request, path)
}

export const GET = handle
export const POST = handle
export const PUT = handle
export const PATCH = handle
export const DELETE = handle
