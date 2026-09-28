// The internal HTTP API: a second server on 127.0.0.1 only, never the browser-facing port, and
// every request must carry the host's secret in X-BB-Secret. JSON in and out; errors are
// {code, message, details}.
import { createServer, type IncomingMessage, type Server } from 'node:http'
import { timingSafeEqual } from 'node:crypto'

export class ApiError extends Error {
  status: number
  code: string
  details: Record<string, unknown>
  constructor(status: number, code: string, message: string, details: Record<string, unknown> = {}) {
    super(message)
    this.status = status
    this.code = code
    this.details = details
  }
}

export interface Request {
  params: string[]
  query: URLSearchParams
  body: any
}

export interface Route {
  method: string
  path: RegExp
  handler: (request: Request) => Promise<unknown>
}

const MAX_BODY = 64 * 1024 * 1024

function readBody(request: IncomingMessage): Promise<any> {
  return new Promise((resolve, reject) => {
    const chunks: Buffer[] = []
    let size = 0
    request.on('data', (chunk: Buffer) => {
      size += chunk.length
      if (size > MAX_BODY) {
        reject(new ApiError(413, 'too_large', 'the request body is too large'))
        request.destroy()
        return
      }
      chunks.push(chunk)
    })
    request.on('end', () => {
      if (!chunks.length) return resolve({})
      try {
        resolve(JSON.parse(Buffer.concat(chunks).toString('utf8')))
      } catch {
        reject(new ApiError(400, 'invalid', 'the body must be JSON'))
      }
    })
    request.on('error', reject)
  })
}

function secretMatches(given: unknown, secret: string): boolean {
  if (typeof given !== 'string') return false
  const a = Buffer.from(given)
  const b = Buffer.from(secret)
  return a.length === b.length && timingSafeEqual(a, b)
}

export function createApi(secret: string, routes: Route[]): Server {
  return createServer(async (request, response) => {
    const send = (status: number, body: unknown) => {
      response.writeHead(status, { 'Content-Type': 'application/json' })
      response.end(JSON.stringify(body))
    }
    try {
      if (!secretMatches(request.headers['x-bb-secret'], secret)) {
        throw new ApiError(401, 'unauthorized', 'missing or wrong X-BB-Secret')
      }
      const url = new URL(request.url || '/', 'http://127.0.0.1')
      for (const route of routes) {
        if (route.method !== request.method) continue
        const m = route.path.exec(url.pathname)
        if (!m) continue
        const body = request.method === 'GET' ? {} : await readBody(request)
        const result = await route.handler({ params: m.slice(1).map(decodeURIComponent), query: url.searchParams, body })
        send(200, result ?? { ok: true })
        return
      }
      throw new ApiError(404, 'not_found', `no route for ${request.method} ${url.pathname}`)
    } catch (error) {
      if (error instanceof ApiError) {
        send(error.status, { code: error.code, message: error.message, details: error.details })
      } else {
        console.error('docservice: request failed', error)
        send(500, { code: 'internal', message: 'the document service could not complete the request', details: {} })
      }
    }
  })
}
