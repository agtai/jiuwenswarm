// Versions: full snapshots of a document's ProseMirror JSON, suggestion and author marks included,
// so a restore brings a document back exactly as it was. One is taken when a document is created,
// after each agent batch, on import and restore, when someone saves one, and when people stop
// editing: every person who changed the document since the last version waits in `pending`, and
// after `idleMs` without a change their edits become one version with them as its authors. A
// version is skipped when nothing changed since the previous one.
import { gunzipSync, gzipSync } from 'node:zlib'
import type { Node as PMNode } from '@tiptap/pm/model'
import { blackboardSchema } from '../schema/extensions.ts'
import type { DocStorage } from '../storage.ts'
import { sha256 } from './markdown.ts'
import type { DocPool } from './pool.ts'

export const VERSION_REASONS = ['created', 'agent_turn', 'idle', 'import', 'restore', 'manual'] as const
export type VersionReason = (typeof VERSION_REASONS)[number]

export interface VersionAuthor {
  id: string
  kind: 'person' | 'agent'
}

export interface VersionInfo {
  id: string
  docId: string
  createdAt: string
  reason: VersionReason
  authors: VersionAuthor[]
  mandateId: string | null
  restoredFrom: string | null
  label: string | null
  size: number
}

export interface VersionMeta {
  reason: VersionReason
  authors: VersionAuthor[]
  mandateId?: string | null
  restoredFrom?: string | null
  label?: string | null
  // Record even when the content equals the previous version's (a named or restored version).
  force?: boolean
}

let counter = 0
export function newVersionId(): string {
  counter += 1
  return 'v' + Date.now().toString(36) + counter.toString(36) + Math.random().toString(36).slice(2, 6)
}

function unique(authors: VersionAuthor[]): VersionAuthor[] {
  const seen = new Map<string, VersionAuthor>()
  for (const a of authors) seen.set(`${a.kind}:${a.id}`, { id: a.id, kind: a.kind })
  return [...seen.values()]
}

interface Pending {
  authors: Map<string, VersionAuthor>
  timer: ReturnType<typeof setTimeout> | null
}

export class Versions {
  private storage: DocStorage
  private pool: DocPool
  private idleMs: number
  private notify: (info: VersionInfo) => void
  private pending = new Map<string, Pending>()

  constructor(storage: DocStorage, pool: DocPool, idleMs: number, notify: (info: VersionInfo) => void) {
    this.storage = storage
    this.pool = pool
    this.idleMs = idleMs
    this.notify = notify
  }

  // A person changed the document: the idle timer starts again.
  touched(docId: string, author: VersionAuthor): void {
    let entry = this.pending.get(docId)
    if (!entry) {
      entry = { authors: new Map(), timer: null }
      this.pending.set(docId, entry)
    }
    entry.authors.set(`${author.kind}:${author.id}`, author)
    if (entry.timer) clearTimeout(entry.timer)
    entry.timer = setTimeout(() => {
      this.flush(docId).catch((error) => console.error(`docservice: idle version of ${docId} failed`, error))
    }, this.idleMs)
    entry.timer.unref?.()
  }

  // People's edits since the last version become one now, before another kind of change (an agent
  // batch, an import, a restore) gets its own version.
  async flush(docId: string): Promise<VersionInfo | null> {
    const entry = this.pending.get(docId)
    if (!entry) return null
    this.pending.delete(docId)
    if (entry.timer) clearTimeout(entry.timer)
    if (!this.storage.exists(docId)) return null
    const doc = await this.pool.read(docId)
    return this.record(docId, doc, { reason: 'idle', authors: [...entry.authors.values()] })
  }

  async flushAll(): Promise<void> {
    for (const docId of [...this.pending.keys()]) {
      await this.flush(docId).catch((error) => console.error(`docservice: version of ${docId} failed at stop`, error))
    }
  }

  forget(docId: string): void {
    const entry = this.pending.get(docId)
    if (entry?.timer) clearTimeout(entry.timer)
    this.pending.delete(docId)
  }

  // Store `doc` as a version of `docId`. Synchronous, so it can run inside a document transaction.
  record(docId: string, doc: PMNode, meta: VersionMeta): VersionInfo | null {
    const json = JSON.stringify(doc.toJSON())
    const digest = sha256(json)
    if (!meta.force && this.storage.lastDigest(docId) === digest) return null
    const info: VersionInfo = {
      id: newVersionId(),
      docId,
      createdAt: new Date().toISOString(),
      reason: meta.reason,
      authors: unique(meta.authors),
      mandateId: meta.mandateId ?? null,
      restoredFrom: meta.restoredFrom ?? null,
      label: meta.label ?? null,
      size: Buffer.byteLength(json),
    }
    this.storage.addVersion(info, digest, gzipSync(Buffer.from(json, 'utf8')))
    this.notify(info)
    return info
  }

  load(docId: string, versionId: string): { info: VersionInfo; doc: PMNode } | null {
    const found = this.storage.getVersion(docId, versionId)
    if (!found) return null
    const json = JSON.parse(gunzipSync(found.snapshot).toString('utf8'))
    return { info: found.info, doc: blackboardSchema().nodeFromJSON(json) }
  }

  previous(docId: string, versionId: string): string | null {
    return this.storage.previousVersionId(docId, versionId)
  }

  list(docId: string, limit: number, before: string | null): VersionInfo[] {
    return this.storage.listVersions(docId, limit, before)
  }
}

// Announces each new version to the host, which tells the workspace. The history itself is in the
// database, so after a few failed tries the announcement is dropped.
export function versionAnnouncer(hostUrl: string | null, secret: string): (info: VersionInfo) => void {
  if (!hostUrl) return () => {}
  const url = `${hostUrl.replace(/\/$/, '')}/blackboard/internal/versions`
  const delays = [500, 2000, 5000]
  const send = async (info: VersionInfo, attempt: number): Promise<void> => {
    try {
      const response = await fetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-BB-Secret': secret },
        body: JSON.stringify(info),
        signal: AbortSignal.timeout(5000),
      })
      if (response.ok || response.status < 500) return
      throw new Error(`host answered ${response.status}`)
    } catch (error) {
      if (attempt >= delays.length) {
        console.error(`docservice: could not announce version ${info.id}`, error)
        return
      }
      await new Promise((resolve) => setTimeout(resolve, delays[attempt]))
      return send(info, attempt + 1)
    }
  }
  return (info) => void send(info, 0)
}
