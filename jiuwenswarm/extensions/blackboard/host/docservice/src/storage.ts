// Yjs document states in SQLite through node:sqlite, so the service has no native module and
// bundles into one file. Hocuspocus's Database extension calls fetch and store.
import { DatabaseSync } from 'node:sqlite'

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
