import assert from 'node:assert/strict'
import { after, before, test } from 'node:test'
import * as Y from 'yjs'
import * as encoding from 'lib0/encoding'
import { DocStorage } from '../src/storage.ts'
import { addParagraph, client, fragmentText, startTestService, token, waitFor, type TestService } from './helpers.ts'

const ALICE = { id: 'u_alice', kind: 'person' }
let service: TestService

before(async () => {
  service = await startTestService()
})

after(async () => {
  await service.stop()
})

async function createDoc(docId: string, markdown = '# Plan\n\nFirst paragraph.\n') {
  const response = await service.call('POST', '/api/docs', { docId, markdown, author: ALICE })
  assert.equal(response.status, 200, JSON.stringify(response.body))
}

test('the API needs the secret and answers health', async () => {
  assert.equal((await service.call('GET', '/api/health', undefined, 'wrong')).status, 401)
  const health = await service.call('GET', '/api/health')
  assert.equal(health.body.ok, true)
  assert.equal(health.body.version, 'test')
})

test('created content is saved before the reply and carries the author', async () => {
  await createDoc('d_saved')
  const stored = service.storage.fetch('d_saved')
  assert.ok(stored)
  const ydoc = new Y.Doc()
  Y.applyUpdate(ydoc, stored!)
  assert.match(fragmentText(ydoc), /First paragraph/)
  const view = await service.call('GET', '/api/docs/d_saved/markdown')
  assert.match(view.body.markdown, /<!-- block:\S+ -->\n# Plan/)
  assert.equal(view.body.blocks.length, 2)
  assert.equal((await service.call('POST', '/api/docs', { docId: 'd_saved', author: ALICE })).status, 409)
  assert.equal((await service.call('GET', '/api/docs/nope/markdown')).status, 404)
})

test('editors write, viewers read live but their writes are dropped', async () => {
  await createDoc('d_roles')
  const editor = client(service.ws, 'd_roles', token('u_alice', 'editor', 'd_roles'))
  const viewer = client(service.ws, 'd_roles', token('u_viola', 'viewer', 'd_roles'))
  try {
    await waitFor(() => editor.synced && viewer.synced)
    assert.equal(editor.scope, 'read-write')
    assert.equal(viewer.scope, 'readonly')

    addParagraph(editor.ydoc, 'From the editor.', ALICE)
    await waitFor(() => fragmentText(viewer.ydoc).includes('From the editor.'))

    addParagraph(viewer.ydoc, 'Viewer write.', { id: 'u_viola', kind: 'person' })
    await new Promise((r) => setTimeout(r, 400))
    const view = await service.call('GET', '/api/docs/d_roles/markdown')
    assert.match(view.body.markdown, /From the editor\./)
    assert.doesNotMatch(view.body.markdown, /Viewer write\./)
    assert.doesNotMatch(fragmentText(editor.ydoc), /Viewer write\./)
  } finally {
    editor.provider.destroy()
    viewer.provider.destroy()
  }
})

test('bad tokens are refused with a reason', async () => {
  await createDoc('d_tokens')
  const cases: [string, string][] = [
    [token('u_alice', 'editor', 'd_tokens', -10), 'token_expired'],
    [token('u_alice', 'editor', 'd_other'), 'token_doc_mismatch'],
    ['not-a-token', 'token_malformed'],
    [token('u_alice', 'editor', 'd_tokens').replace(/\.[^.]+$/, '.AAAA'), 'token_bad_signature'],
  ]
  for (const [value, reason] of cases) {
    const c = client(service.ws, 'd_tokens', value)
    try {
      await waitFor(() => c.failed !== null)
      assert.equal(c.failed, reason)
    } finally {
      c.provider.destroy()
    }
  }
  // A browser cannot create a document by connecting to it.
  const ghost = client(service.ws, 'd_never_created', token('u_alice', 'editor', 'd_never_created'))
  try {
    await waitFor(() => ghost.failed !== null)
    assert.equal(ghost.failed, 'doc_not_found')
  } finally {
    ghost.provider.destroy()
  }
})

test('the author guard refuses marks that claim someone else', async () => {
  await createDoc('d_guard')
  const mallory = client(service.ws, 'd_guard', token('u_mallory', 'editor', 'd_guard'))
  try {
    await waitFor(() => mallory.synced)
    addParagraph(mallory.ydoc, 'Forged as Alice.', ALICE)
    addParagraph(mallory.ydoc, 'Forged agent.', { id: 'u_mallory', kind: 'agent' })
    await new Promise((r) => setTimeout(r, 400))
    const view = await service.call('GET', '/api/docs/d_guard/markdown')
    assert.doesNotMatch(view.body.markdown, /Forged/)
  } finally {
    mallory.provider.destroy()
  }

  // The same forged update sent as a SyncReply (type 4) instead of Sync (type 0).
  await new Promise<void>((resolve) => {
    const ws = new WebSocket(service.ws)
    ws.binaryType = 'arraybuffer'
    ws.onopen = () => {
      const auth = encoding.createEncoder()
      encoding.writeVarString(auth, 'd_guard')
      encoding.writeVarUint(auth, 2)
      encoding.writeVarUint(auth, 0)
      encoding.writeVarString(auth, token('u_trudy', 'editor', 'd_guard'))
      encoding.writeVarString(auth, '4.7.0')
      ws.send(encoding.toUint8Array(auth))
      setTimeout(() => {
        const d = new Y.Doc()
        addParagraph(d, 'Sent as SyncReply.', ALICE)
        const message = encoding.createEncoder()
        encoding.writeVarString(message, 'd_guard')
        encoding.writeVarUint(message, 4)
        encoding.writeVarUint(message, 2)
        encoding.writeVarUint8Array(message, Y.encodeStateAsUpdate(d))
        ws.send(encoding.toUint8Array(message))
        setTimeout(() => {
          ws.close()
          resolve()
        }, 400)
      }, 300)
    }
  })
  const view = await service.call('GET', '/api/docs/d_guard/markdown')
  assert.doesNotMatch(view.body.markdown, /Sent as SyncReply/)
})

test("typing after someone's text and splitting their paragraph keep everyone's credit and pass", async () => {
  await createDoc('d_split', 'First paragraph.\n')
  const BOB = { id: 'u_bob', kind: 'person' }
  const bob = client(service.ws, 'd_split', token('u_bob', 'editor', 'd_split'))
  try {
    await waitFor(() => bob.synced)
    const fragment = bob.ydoc.getXmlFragment('default')
    const text = (fragment.get(0) as Y.XmlElement).get(0) as Y.XmlText
    // Yjs follows Bob's insertion with a format item that gives the rest back to Alice.
    text.insert(text.length, ' Bob adds this.', { author: BOB })
    await waitFor(async () => /Bob adds this/.test((await service.call('GET', '/api/docs/d_split/markdown')).body.markdown))

    // Enter inside Alice's words: the binding deletes the tail and recreates it in a new paragraph.
    bob.ydoc.transact(() => {
      text.delete(6, 10)
      const paragraph = new Y.XmlElement('paragraph')
      const tail = new Y.XmlText()
      tail.insert(0, 'paragraph.', { author: ALICE })
      paragraph.insert(0, [tail])
      fragment.insert(1, [paragraph])
    })
    await waitFor(async () => /First[^\n]*\n\n<!-- block:\S+ -->\nparagraph\./.test((await service.call('GET', '/api/docs/d_split/markdown')).body.markdown))

    // Adding words credited to Alice is still refused.
    text.insert(0, 'Alice agrees. ', { author: ALICE })
    await new Promise((r) => setTimeout(r, 400))
    assert.doesNotMatch((await service.call('GET', '/api/docs/d_split/markdown')).body.markdown, /Alice agrees/)
  } finally {
    bob.provider.destroy()
  }
})

test('presence lists connections, and a recheck applies a demotion live', async () => {
  await createDoc('d_recheck')
  let role = 'editor'
  const bob = client(service.ws, 'd_recheck', () => token('u_bob', role, 'd_recheck'))
  try {
    await waitFor(() => bob.synced)
    const presence = await service.call('GET', '/api/docs/d_recheck/presence')
    assert.deepEqual(presence.body.connections, [{ userId: 'u_bob', kind: 'person', readOnly: false }])

    role = 'viewer'
    const recheck = await service.call('POST', '/api/docs/d_recheck/recheck', { userId: 'u_bob' })
    assert.equal(recheck.body.rechecked, 1)
    await waitFor(async () => (await service.call('GET', '/api/docs/d_recheck/presence')).body.connections[0]?.readOnly === true)
    addParagraph(bob.ydoc, 'After demotion.', { id: 'u_bob', kind: 'person' })
    await new Promise((r) => setTimeout(r, 400))
    assert.doesNotMatch((await service.call('GET', '/api/docs/d_recheck/markdown')).body.markdown, /After demotion/)
  } finally {
    bob.provider.destroy()
  }
})

test('a recheck with a role applies it even when the browser keeps an old token; revoke disconnects', async () => {
  await createDoc('d_role')
  const bob = client(service.ws, 'd_role', token('u_bob', 'editor', 'd_role'))
  try {
    await waitFor(() => bob.synced)
    await service.call('POST', '/api/docs/d_role/recheck', { userId: 'u_bob', role: 'viewer' })
    const presence = await service.call('GET', '/api/docs/d_role/presence')
    assert.equal(presence.body.connections[0].readOnly, true)
    await new Promise((r) => setTimeout(r, 200))
    assert.equal((await service.call('GET', '/api/docs/d_role/presence')).body.connections[0].readOnly, true)

    await service.call('POST', '/api/docs/d_role/recheck', { userId: 'u_bob', revoke: true })
    await waitFor(async () => (await service.call('GET', '/api/docs/d_role/presence')).body.connections.length === 0)
  } finally {
    bob.provider.destroy()
  }
  const again = client(service.ws, 'd_role', token('u_bob', 'editor', 'd_role'))
  try {
    await new Promise((r) => setTimeout(r, 400))
    assert.equal(again.synced, false)
  } finally {
    again.provider.destroy()
  }
})

test('import replaces the content for everyone connected', async () => {
  await createDoc('d_import')
  const reader = client(service.ws, 'd_import', token('u_alice', 'editor', 'd_import'))
  try {
    await waitFor(() => reader.synced)
    const result = await service.call('POST', '/api/docs/d_import/import', { markdown: '## Replaced\n\n<b>raw</b>\n', author: ALICE })
    assert.equal(result.status, 200)
    assert.equal(result.body.rawHtml, true)
    await waitFor(() => fragmentText(reader.ydoc).includes('Replaced'))
    assert.doesNotMatch(fragmentText(reader.ydoc), /First paragraph/)
    const bad = await service.call('POST', '/api/docs/d_import/import', { author: ALICE })
    assert.equal(bad.status, 400)
  } finally {
    reader.provider.destroy()
  }
})

test('delete closes connections and the document stays gone', async () => {
  await createDoc('d_delete')
  const c = client(service.ws, 'd_delete', token('u_alice', 'editor', 'd_delete'))
  try {
    await waitFor(() => c.synced)
    const deleted = await service.call('DELETE', '/api/docs/d_delete')
    assert.equal(deleted.body.deleted, true)
    await new Promise((r) => setTimeout(r, 300))
    assert.equal(service.storage.exists('d_delete'), false)
    assert.equal((await service.call('GET', '/api/docs/d_delete/markdown')).status, 404)
  } finally {
    c.provider.destroy()
  }
})

test('stopping the service saves what was typed', async () => {
  const own = await startTestService()
  const response = await own.call('POST', '/api/docs', { docId: 'd_stop', markdown: 'Start.\n', author: ALICE })
  assert.equal(response.status, 200)
  const c = client(own.ws, 'd_stop', token('u_alice', 'editor', 'd_stop'))
  await waitFor(() => c.synced)
  addParagraph(c.ydoc, 'Typed before the stop.', ALICE)
  await waitFor(async () => (await own.call('GET', '/api/docs/d_stop/markdown')).body.markdown.includes('Typed before'))
  c.provider.destroy()
  await own.stop()
  const storage = new DocStorage(own.config.dbPath)
  const ydoc = new Y.Doc()
  Y.applyUpdate(ydoc, storage.fetch('d_stop')!)
  storage.close()
  assert.match(fragmentText(ydoc), /Typed before the stop\./)
})
