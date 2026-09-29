// Yjs document states in SQLite through node:sqlite, so the service has no native module and
// bundles into one file. Hocuspocus's Database extension calls fetch and store. Versions (full
// snapshots of a document) live in the same file.
import { DatabaseSync } from 'node:sqlite'
import type { VersionInfo } from './docs/versions.ts'

const VERSION_COLUMNS = 'id, doc_id, created_at, reason, authors, mandate_id, restored_from, label, size'

function versionRow(row: any): VersionInfo {
  return {
    id: row.id,
    docId: row.doc_id,
    createdAt: row.created_at,
    reason: row.reason,
    authors: JSON.parse(row.authors),
    mandateId: row.mandate_id ?? null,
    restoredFrom: row.restored_from ?? null,
    label: row.label ?? null,
    size: Number(row.size),
  }
}

export class DocStorage {
  private db: DatabaseSync
  // Deleted in this process: a connection closing after the delete still tries to save once.
  private deleted = new Set<string>()

  constructor(path: string) {
    this.db = new DatabaseSync(path)
    this.db.exec('PRAGMA journal_mode = WAL')
    this.db.exec('PRAGMA busy_timeout = 5000')
    this.db.exec(
      'CREATE TABLE IF NOT EXISTS documents (name TEXT PRIMARY KEY, data BLOB NOT NULL, updated_at TEXT NOT NULL)',
    )
    // The host's last word on a person's access to a document (role NULL: removed), so a token
    // minted before it cannot bring the old role back.
    this.db.exec(
      'CREATE TABLE IF NOT EXISTS access (doc TEXT NOT NULL, uid TEXT NOT NULL, role TEXT, at INTEGER NOT NULL, PRIMARY KEY (doc, uid))',
    )
    // Ordered by rowid: ids made in the same millisecond do not sort by time.
    this.db.exec(
      'CREATE TABLE IF NOT EXISTS versions (id TEXT PRIMARY KEY, doc_id TEXT NOT NULL, created_at TEXT NOT NULL,' +
        ' reason TEXT NOT NULL, authors TEXT NOT NULL, mandate_id TEXT, restored_from TEXT, label TEXT,' +
        ' digest TEXT NOT NULL, snapshot BLOB NOT NULL, size INTEGER NOT NULL)',
    )
    this.db.exec('CREATE INDEX IF NOT EXISTS versions_doc ON versions(doc_id)')
  }

  fetch(name: string): Uint8Array | null {
    const row = this.db.prepare('SELECT data FROM documents WHERE name = ?').get(name) as { data: Uint8Array } | undefined
    return row ? new Uint8Array(row.data) : null
  }

  store(name: string, data: Uint8Array): void {
    if (this.deleted.has(name)) return
    this.db
      .prepare(
        'INSERT INTO documents (name, data, updated_at) VALUES (?, ?, ?)' +
          ' ON CONFLICT(name) DO UPDATE SET data = excluded.data, updated_at = excluded.updated_at',
      )
      .run(name, data, new Date().toISOString())
  }

  exists(name: string): boolean {
    return Boolean(this.db.prepare('SELECT 1 FROM documents WHERE name = ?').get(name))
  }

  delete(name: string): void {
    this.deleted.add(name)
    this.db.prepare('DELETE FROM documents WHERE name = ?').run(name)
    this.db.prepare('DELETE FROM access WHERE doc = ?').run(name)
    this.db.prepare('DELETE FROM versions WHERE doc_id = ?').run(name)
  }

  addVersion(info: VersionInfo, digest: string, snapshot: Uint8Array): void {
    this.db
      .prepare(`INSERT INTO versions (${VERSION_COLUMNS}, digest, snapshot) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`)
      .run(
        info.id,
        info.docId,
        info.createdAt,
        info.reason,
        JSON.stringify(info.authors),
        info.mandateId,
        info.restoredFrom,
        info.label,
        info.size,
        digest,
        snapshot,
      )
  }

  lastDigest(docId: string): string | null {
    const row = this.db.prepare('SELECT digest FROM versions WHERE doc_id = ? ORDER BY rowid DESC LIMIT 1').get(docId) as any
    return row ? String(row.digest) : null
  }

  // Newest first; `before` is a version id, for the next page.
  listVersions(docId: string, limit: number, before: string | null): VersionInfo[] {
    const rows = before
      ? this.db
          .prepare(
            `SELECT ${VERSION_COLUMNS} FROM versions WHERE doc_id = ? AND rowid < (SELECT rowid FROM versions WHERE id = ?) ORDER BY rowid DESC LIMIT ?`,
          )
          .all(docId, before, limit)
      : this.db.prepare(`SELECT ${VERSION_COLUMNS} FROM versions WHERE doc_id = ? ORDER BY rowid DESC LIMIT ?`).all(docId, limit)
    return rows.map(versionRow)
  }

  getVersion(docId: string, id: string): { info: VersionInfo; snapshot: Uint8Array } | null {
    const row = this.db.prepare(`SELECT ${VERSION_COLUMNS}, snapshot FROM versions WHERE doc_id = ? AND id = ?`).get(docId, id) as any
    return row ? { info: versionRow(row), snapshot: new Uint8Array(row.snapshot) } : null
  }

  // The version just before `id`, for "changes since the previous version".
  previousVersionId(docId: string, id: string): string | null {
    const row = this.db
      .prepare('SELECT id FROM versions WHERE doc_id = ? AND rowid < (SELECT rowid FROM versions WHERE id = ?) ORDER BY rowid DESC LIMIT 1')
      .get(docId, id) as any
    return row ? String(row.id) : null
  }

  setAccess(doc: string, uid: string, role: string | null, at: number): void {
    this.db
      .prepare('INSERT INTO access (doc, uid, role, at) VALUES (?, ?, ?, ?) ON CONFLICT(doc, uid) DO UPDATE SET role = excluded.role, at = excluded.at')
      .run(doc, uid, role, at)
  }

  access(doc: string, uid: string): { role: string | null; at: number } | null {
    const row = this.db.prepare('SELECT role, at FROM access WHERE doc = ? AND uid = ?').get(doc, uid) as any
    return row ? { role: row.role ?? null, at: Number(row.at) } : null
  }

  // A new document under a name deleted earlier in this process.
  revive(name: string): void {
    this.deleted.delete(name)
  }

  close(): void {
    this.db.close()
  }
}
