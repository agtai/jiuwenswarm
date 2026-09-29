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
import { stampAwareness } from './hooks/awareness.ts'
import { originAllowed } from './origins.ts'
import { DocStorage } from './storage.ts'

// Tokens last an hour; every connection shows its current token again this often, so an expired
// token or a changed role takes effect during long sessions too.
const RECHECK_INTERVAL_MS = 30 * 60 * 1000
const PRUNE_INTERVAL_MS = 6 * 60 * 60 * 1000

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
    // A page from an origin the host does not allow gets no WebSocket at all.
    async onUpgrade({ request, socket }: any) {
      const origin = request.headers?.origin
      if (originAllowed(origin, config.allowedOrigins, config.allowAnyOrigin)) return
      console.warn(`blackboard docs: refused a connection from origin ${String(origin).slice(0, 200)}`)
      socket.write('HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n')
      socket.destroy()
      // Hocuspocus rethrows only truthy errors; null just stops the upgrade.
      throw null
    },
    async onAuthenticate({ token, documentName, connectionConfig }: any) {
      const claims = verifyDocToken(token, config.docSecret)
      if (claims.doc !== documentName) throw new TokenError('token_doc_mismatch')
      // Only the host creates documents (through the API); a browser cannot bring one into being.
      if (!storage.exists(documentName) && !server.hocuspocus.documents.has(documentName)) throw new TokenError('doc_not_found')
      const role = roleFor(claims)
      connectionConfig.readOnly = !WRITE_ROLES.includes(role)
      return { userId: claims.uid, name: claims.name ?? '', workspaceId: claims.ws, role, kind: 'person' }
    },
    // Token refresh, role changes and revocation on a live connection (connection.requestToken()).
    async onTokenSync({ token, documentName, connection }: any) {
      const claims = verifyDocToken(token, config.docSecret)
      if (claims.doc !== documentName || claims.uid !== connection.context?.userId) throw new TokenError('token_doc_mismatch')
      const role = roleFor(claims)
      connection.readOnly = !WRITE_ROLES.includes(role)
      connection.context.role = role
      if (typeof claims.name === 'string') connection.context.name = claims.name
    },
    async beforeHandleMessage(payload: any) {
      authorGuard(payload)
    },
    async beforeHandleAwareness(payload: any) {
      stampAwareness(payload)
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
  const prune = () => {
    if (config.versionRetentionDays <= 0) return
    const cutoff = new Date(Date.now() - config.versionRetentionDays * 86400_000).toISOString()
    const removed = storage.pruneVersions(cutoff)
    if (removed) console.log(`blackboard docs: removed ${removed} versions older than ${config.versionRetentionDays} days`)
  }
  prune()
  const pruner = setInterval(prune, PRUNE_INTERVAL_MS)
  pruner.unref()

  const stop = () => {
    stopping ??= (async () => {
      clearInterval(recheck)
      clearInterval(pruner)
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
      chromium: config.chromium,
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
