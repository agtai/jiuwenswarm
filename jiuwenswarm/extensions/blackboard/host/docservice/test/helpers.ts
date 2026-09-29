import { mkdtempSync } from 'node:fs'
import { createServer } from 'node:net'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import * as Y from 'yjs'
import { HocuspocusProvider } from '@hocuspocus/provider'
import { mintDocToken } from '../src/auth.ts'
import type { Config } from '../src/config.ts'
import { startService, type Service } from '../src/service.ts'

export const DOC_SECRET = 'test-doc-secret'
export const API_SECRET = 'test-api-secret'

export async function freePort(): Promise<number> {
  return new Promise((resolve, reject) => {
    const server = createServer()
    server.once('error', reject)
    server.listen(0, '127.0.0.1', () => {
      const port = (server.address() as any).port
      server.close(() => resolve(port))
    })
  })
}

export async function waitFor(check: () => boolean | Promise<boolean>, ms = 5000): Promise<void> {
  const deadline = Date.now() + ms
  while (Date.now() < deadline) {
    if (await check()) return
    await new Promise((r) => setTimeout(r, 25))
  }
  throw new Error('condition not met in time')
}

export interface TestService extends Service {
  config: Config
  ws: string
  api: Service['api']
  call: (method: string, path: string, body?: unknown, secret?: string) => Promise<{ status: number; body: any }>
}

export async function startTestService(
  dir = mkdtempSync(join(tmpdir(), 'bb-docservice-')),
  overrides: Partial<Config> = {},
): Promise<TestService> {
  const config: Config = {
    port: await freePort(),
    bind: '127.0.0.1',
    apiPort: await freePort(),
    dbPath: join(dir, 'docs.db'),
    docSecret: DOC_SECRET,
    apiSecret: API_SECRET,
    parentPid: null,
    version: 'test',
    hostUrl: null,
    idleMs: 200,
    chromium: null,
    ...overrides,
  }
  const service = await startService(config)
  const call = async (method: string, path: string, body?: unknown, secret = API_SECRET) => {
    const response = await fetch(`http://127.0.0.1:${config.apiPort}${path}`, {
      method,
      headers: { 'X-BB-Secret': secret, 'Content-Type': 'application/json' },
      body: body === undefined ? undefined : JSON.stringify(body),
    })
    return { status: response.status, body: await response.json() }
  }
  return { ...service, config, ws: `ws://127.0.0.1:${config.port}`, call }
}

export const token = (uid: string, role: string, doc: string, ttl = 3600) => mintDocToken({ uid, ws: 'ws_1', doc, role }, DOC_SECRET, ttl)

export interface Client {
  ydoc: Y.Doc
  provider: HocuspocusProvider
  scope: string | null
  failed: string | null
  synced: boolean
}

// A Node client; `tokenValue` may be a string or a function, as in the browser.
export function client(ws: string, doc: string, tokenValue: string | (() => string | Promise<string>)): Client {
  const ydoc = new Y.Doc()
  const c: Client = { ydoc, provider: null as any, scope: null, failed: null, synced: false }
  c.provider = new HocuspocusProvider({
    url: ws,
    name: doc,
    document: ydoc,
    token: tokenValue as any,
    onAuthenticated: (d: any) => {
      c.scope = d?.scope ?? null
    },
    onAuthenticationFailed: (d: any) => {
      c.failed = d?.reason ?? 'failed'
    },
    onSynced: () => {
      c.synced = true
    },
  } as any)
  return c
}

export function fragmentText(ydoc: Y.Doc): string {
  return ydoc.getXmlFragment('default').toString()
}

// Add a paragraph through the Y data, the way a browser editor would, with author mark attrs.
export function addParagraph(ydoc: Y.Doc, text: string, author: Record<string, unknown> | null): void {
  ydoc.transact(() => {
    const paragraph = new Y.XmlElement('paragraph')
    const yText = new Y.XmlText()
    yText.insert(0, text, author ? { author } : {})
    paragraph.insert(0, [yText])
    ydoc.getXmlFragment('default').push([paragraph])
  })
}

// Deep copy without block ids, for structural comparison.
export function stripIds(node: any): any {
  if (Array.isArray(node)) return node.map(stripIds)
  if (!node || typeof node !== 'object') return node
  const out: any = {}
  for (const [k, v] of Object.entries(node)) {
    if (k === 'attrs') {
      const attrs: any = { ...(v as any) }
      delete attrs.id
      if (Object.keys(attrs).length) out.attrs = stripIds(attrs)
    } else {
      out[k] = stripIds(v)
    }
  }
  return out
}
