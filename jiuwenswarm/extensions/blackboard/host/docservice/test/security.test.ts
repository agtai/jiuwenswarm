// Milestone 8 hardening: which pages may connect, what a caret may claim, and version retention.
import assert from 'node:assert/strict'
import { request } from 'node:http'
import { mkdtempSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { after, before, test } from 'node:test'
import { originAllowed } from '../src/origins.ts'
import { DocStorage } from '../src/storage.ts'
import { client, startTestService, token, waitFor, type TestService } from './helpers.ts'

const ALICE = { id: 'u_alice', kind: 'person' }
let service: TestService

before(async () => {
  service = await startTestService(undefined, { allowedOrigins: ['https://team.example.com'] })
})

after(async () => {
  await service.stop()
})

// The HTTP status a WebSocket upgrade from `origin` gets (101 when it is accepted).
function upgradeStatus(port: number, origin: string | null): Promise<number> {
  return new Promise((resolve, reject) => {
    const headers: Record<string, string> = {
      Connection: 'Upgrade',
      Upgrade: 'websocket',
      'Sec-WebSocket-Version': '13',
      'Sec-WebSocket-Key': Buffer.from('0123456789abcdef').toString('base64'),
    }
    if (origin) headers.Origin = origin
    const req = request({ host: '127.0.0.1', port, path: '/', headers })
    req.on('upgrade', (res, socket) => {
      socket.destroy()
      resolve(res.statusCode ?? 0)
    })
    req.on('response', (res) => {
      res.resume()
      resolve(res.statusCode ?? 0)
    })
    req.on('error', (error: any) => (error.code === 'ECONNRESET' ? resolve(0) : reject(error)))
    req.end()
  })
}

test('origins: loopback pages, configured ones, and clients without an origin', () => {
  assert.ok(originAllowed(undefined, [], false))
  assert.ok(originAllowed('http://127.0.0.1:5173', [], false))
  assert.ok(originAllowed('http://localhost:19000/', [], false))
  assert.ok(originAllowed('http://[::1]:5173', [], false))
  assert.ok(originAllowed('https://Team.example.com', ['https://team.example.com'], false))
  assert.ok(!originAllowed('https://evil.example', ['https://team.example.com'], false))
  assert.ok(!originAllowed('null', [], false))
  assert.ok(!originAllowed('file://', [], false))
  assert.ok(originAllowed('https://evil.example', [], true))
})

test('a page from another origin gets no WebSocket', async () => {
  const port = service.config.port
  assert.equal(await upgradeStatus(port, 'http://127.0.0.1:5173'), 101)
  assert.equal(await upgradeStatus(port, 'https://team.example.com'), 101)
  assert.equal(await upgradeStatus(port, null), 101)
  assert.notEqual(await upgradeStatus(port, 'https://evil.example'), 101)
})

test('a caret shows the name and id from the token, never an agent', async () => {
  const response = await service.call('POST', '/api/docs', { docId: 'd_caret', markdown: 'Hello.\n', author: ALICE })
  assert.equal(response.status, 200)
  const mallory = client(service.ws, 'd_caret', token('u_mallory', 'editor', 'd_caret', 3600, 'Mallory'))
  const alice = client(service.ws, 'd_caret', token('u_alice', 'editor', 'd_caret', 3600, 'Alice'))
  try {
    await waitFor(() => mallory.synced && alice.synced)
    mallory.provider.awareness!.setLocalState({
      user: { id: 'u_alice', name: 'Alice', kind: 'agent', status: 'writing' },
      cursor: null,
    })
    const seen = () =>
      [...alice.provider.awareness!.getStates().entries()]
        .filter(([id]) => id === mallory.ydoc.clientID)
        .map(([, state]) => state as any)[0]
    await waitFor(() => seen()?.user !== undefined)
    assert.deepEqual(seen().user, { id: 'u_mallory', name: 'Mallory' })
  } finally {
    mallory.provider.destroy()
    alice.provider.destroy()
  }
})

test('retention removes old versions but keeps named ones and the latest', () => {
  const storage = new DocStorage(join(mkdtempSync(join(tmpdir(), 'bb-retention-')), 'docs.db'))
  const add = (id: string, docId: string, createdAt: string, label: string | null = null) =>
    storage.addVersion(
      { id, docId, createdAt, reason: 'idle', authors: [], mandateId: null, restoredFrom: null, label, size: 1 },
      id,
      new Uint8Array([0]),
    )
  add('v1', 'd1', '2026-01-01T00:00:00.000Z')
  add('v2', 'd1', '2026-01-02T00:00:00.000Z', 'Draft for review')
  add('v3', 'd1', '2026-01-03T00:00:00.000Z')
  add('v4', 'd1', '2026-09-01T00:00:00.000Z')
  add('w1', 'd2', '2026-01-01T00:00:00.000Z')
  try {
    assert.equal(storage.pruneVersions('2026-06-01T00:00:00.000Z'), 2)
    assert.deepEqual(storage.listVersions('d1', 10, null).map((v) => v.id), ['v4', 'v2'])
    assert.deepEqual(storage.listVersions('d2', 10, null).map((v) => v.id), ['w1'])
  } finally {
    storage.close()
  }
})
