// Document tokens: base64url(header).base64url(payload).base64url(HMAC-SHA256) with payload
// {uid, ws, doc, role, exp}. The host mints them (common/tokens.py); the service only verifies.
import { createHmac, timingSafeEqual } from 'node:crypto'

export const ROLES = ['owner', 'editor', 'commenter', 'viewer']
export const WRITE_ROLES = ['owner', 'editor']

export interface DocClaims {
  uid: string
  // The person's display name, stamped on their caret (hooks/awareness.ts).
  name?: string
  ws: string
  doc: string
  role: string
  exp: number
  iat?: number
}

// The reason reaches the browser, which uses it to decide whether to fetch a new token.
export class TokenError extends Error {
  reason: string
  constructor(reason: string) {
    super(reason)
    this.reason = reason
  }
}

export function verifyDocToken(token: unknown, secret: string, now = Math.floor(Date.now() / 1000)): DocClaims {
  const parts = String(token || '').split('.')
  if (parts.length !== 3) throw new TokenError('token_malformed')
  const [header, payload, sig] = parts
  const expected = createHmac('sha256', secret).update(`${header}.${payload}`).digest()
  const given = Buffer.from(sig, 'base64url')
  if (given.length !== expected.length || !timingSafeEqual(given, expected)) throw new TokenError('token_bad_signature')
  let claims: DocClaims
  try {
    claims = JSON.parse(Buffer.from(payload, 'base64url').toString('utf8'))
  } catch {
    throw new TokenError('token_malformed')
  }
  if (!claims || typeof claims.exp !== 'number' || typeof claims.uid !== 'string' || typeof claims.doc !== 'string') {
    throw new TokenError('token_malformed')
  }
  if (claims.exp < now) throw new TokenError('token_expired')
  return claims
}

// For tests: the same format the host mints.
export function mintDocToken(claims: Omit<DocClaims, 'exp' | 'iat'>, secret: string, ttlSeconds = 3600): string {
  const b64 = (text: string) => Buffer.from(text).toString('base64url')
  const header = b64(JSON.stringify({ alg: 'HS256', typ: 'BBDOC' }))
  const now = Math.floor(Date.now() / 1000)
  const payload = b64(JSON.stringify({ ...claims, iat: now, exp: now + ttlSeconds }))
  const sig = createHmac('sha256', secret).update(`${header}.${payload}`).digest('base64url')
  return `${header}.${payload}.${sig}`
}
