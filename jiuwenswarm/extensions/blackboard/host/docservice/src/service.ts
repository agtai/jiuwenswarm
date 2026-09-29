// The document service: Hocuspocus for browsers (token auth, read-only roles, the author guard) and
// the internal HTTP API for the host.
import type { Server as HttpServer } from 'node:http'
import { Server } from '@hocuspocus/server'
import { Database } from '@hocuspocus/extension-database'
import { WRITE_ROLES, TokenError, verifyDocToken, type DocClaims } from './auth.ts'
import { docRoutes } from './api/docs.ts'
import { createApi } from './api/http.ts'
import { versionRoutes } from './api/versions.ts'
import type { Config } from './config.ts'
import { DocPool } from './docs/pool.ts'
import { Versions, versionAnnouncer } from './docs/versions.ts'
import { authorGuard } from './hooks/authorGuard.ts'
import { DocStorage } from './storage.ts'

// Tokens last an hour; every connection shows its current token again this often, so an expired
// token or a changed role takes effect during long sessions too.
const RECHECK_INTERVAL_MS = 30 * 60 * 1000

export interface Service {
  server: Server
  pool: DocPool
  storage: DocStorage
  versions: Versions
  api: HttpServer
  stop: () => Promise<void>
}

// onShutdown runs after POST /api/shutdown has stopped everything (the process entry exits there).
export async function startService(config: Config, { onShutdown = () => {} }: { onShutdown?: () => void } = {}): Promise<Service> {
  const storage = new DocStorage(config.dbPath)
  let stopping: Promise<void> | null = null

  // A token minted before the host's last access change for this person gets the host's role.
  const roleFor = (claims: DocClaims): string => {
    const pinned = storage.access(claims.doc, claims.uid)
    if (!pinned || (claims.iat ?? 0) > pinned.at) return claims.role
    if (pinned.role === null) throw new TokenError('access_revoked')
    return pinned.role
  }

  const server = new Server({
    port: config.port,
    address: config.bind,
    quiet: true,
    stopOnSignals: false,
    debounce: 2000,
    maxDebounce: 10000,
    extensions: [
      new Database({
        fetch: async ({ documentName }) => storage.fetch(documentName),
        store: async ({ documentName, state }) => storage.store(documentName, state),
      }),
    ],
    async onAuthenticate({ token, documentName, connectionConfig }: any) {
      const claims = verifyDocToken(token, config.docSecret)
      if (claims.doc !== documentName) throw new TokenError('token_doc_mismatch')
      // Only the host creates documents (through the API); a browser cannot bring one into being.
      if (!storage.exists(documentName) && !server.hocuspocus.documents.has(documentName)) throw new TokenError('doc_not_found')
      const role = roleFor(claims)
      connectionConfig.readOnly = !WRITE_ROLES.includes(role)
      return { userId: claims.uid, workspaceId: claims.ws, role, kind: 'person' }
    },
    // Token refresh, role changes and revocation on a live connection (connection.requestToken()).
    async onTokenSync({ token, documentName, connection }: any) {
      const claims = verifyDocToken(token, config.docSecret)
      if (claims.doc !== documentName || claims.uid !== connection.context?.userId) throw new TokenError('token_doc_mismatch')
      const role = roleFor(claims)
      connection.readOnly = !WRITE_ROLES.includes(role)
      connection.context.role = role
    },
    async beforeHandleMessage(payload: any) {
      authorGuard(payload)
    },
    // A person's edit starts the idle wait for a version; the API's own changes take theirs directly.
    async onChange({ documentName, context }: any) {
      if (context?.kind === 'person' && typeof context.userId === 'string') {
        versions.touched(documentName, { id: context.userId, kind: 'person' })
      }
    },
  } as any)
  await server.listen()

  const pool = new DocPool(server.hocuspocus)
  const versions = new Versions(storage, pool, config.idleMs, versionAnnouncer(config.hostUrl, config.apiSecret))
  const recheck = setInterval(() => {
    for (const document of server.hocuspocus.documents.values()) {
      for (const connection of document.getConnections()) (connection as any).requestToken()
    }
  }, RECHECK_INTERVAL_MS)
  recheck.unref()

  const stop = () => {
    stopping ??= (async () => {
      clearInterval(recheck)
      await new Promise<void>((resolve) => api.close(() => resolve()))
      await versions.flushAll()
      // destroy() closes connections and stores every loaded document first.
      await server.destroy()
      storage.close()
    })()
    return stopping
  }

  const api = createApi(config.apiSecret, [
    ...docRoutes({
      hocuspocus: server.hocuspocus,
      pool,
      storage,
      versions,
      version: config.version,
      shutdown: () => void stop().then(onShutdown),
    }),
    ...versionRoutes({ hocuspocus: server.hocuspocus, pool, storage, versions, chromium: config.chromium }),
  ])
  await new Promise<void>((resolve, reject) => {
    api.once('error', reject)
    api.listen(config.apiPort, '127.0.0.1', () => resolve())
  })

  return { server, pool, storage, versions, api, stop }
}
