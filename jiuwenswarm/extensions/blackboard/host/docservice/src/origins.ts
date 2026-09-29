// Which web pages may open a live document. Browsers always send Origin on a WebSocket; members'
// web apps normally run on their own machine (a loopback origin), so other origins need the host's
// allowed_origins or allow_any_origin. The same rule as common/origins.py.
const LOOPBACK = new Set(['localhost', '127.0.0.1', '[::1]', '::1'])

export function normalizeOrigin(origin: string): string {
  return origin.trim().toLowerCase().replace(/\/+$/, '')
}

export function originAllowed(origin: string | null | undefined, allowed: string[], allowAny: boolean): boolean {
  if (!origin || allowAny) return true
  const value = normalizeOrigin(origin)
  if (allowed.includes(value)) return true
  let url: URL
  try {
    url = new URL(value)
  } catch {
    return false
  }
  if (url.protocol !== 'http:' && url.protocol !== 'https:') return false
  return LOOPBACK.has(url.hostname) || url.hostname.endsWith('.localhost')
}
