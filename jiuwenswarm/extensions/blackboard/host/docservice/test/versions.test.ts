// Versions (when they are taken, by whom), the block diff, restore, the announcement to the host,
// and the three export formats.
import assert from 'node:assert/strict'
import { createServer, type Server } from 'node:http'
import { after, before, test } from 'node:test'
import JSZip from 'jszip'
import { diffDocs } from '../src/docs/diff.ts'
import { findChromium, pictureOf } from '../src/docs/export.ts'
import { importDoc } from '../src/docs/markdown.ts'
import { blackboardSchema } from '../src/schema/extensions.ts'
import { API_SECRET, addParagraph, client, freePort, startTestService, token, waitFor, type TestService } from './helpers.ts'

const ALICE = { id: 'u_alice', kind: 'person' }
const BOB = { id: 'u_bob', kind: 'person' }
const AGENT = { id: 'u_alice', kind: 'agent' }
const DOC = '# Plan\n\nWe ship once the tests pass.\n\nSecond paragraph.\n\nThird paragraph.\n'

let service: TestService
let hook: Server
const announced: Array<{ secret: unknown; body: any }> = []

before(async () => {
  const port = await freePort()
  hook = createServer((request, response) => {
    let data = ''
    request.on('data', (chunk) => (data += chunk))
    request.on('end', () => {
      announced.push({ secret: request.headers['x-bb-secret'], body: JSON.parse(data) })
      response.end('{}')
    })
  })
  await new Promise<void>((resolve) => hook.listen(port, '127.0.0.1', () => resolve()))
  service = await startTestService(undefined, { hostUrl: `http://127.0.0.1:${port}` })
})

after(async () => {
  await service.stop()
  await new Promise((resolve) => hook.close(resolve))
})

async function createDoc(on: TestService, docId: string, markdown = DOC) {
  const response = await on.call('POST', '/api/docs', { docId, markdown, author: ALICE })
  assert.equal(response.status, 200, JSON.stringify(response.body))
}

const versionsOf = async (on: TestService, docId: string) => (await on.call('GET', `/api/docs/${docId}/versions`)).body.versions
const blocks = async (on: TestService, docId: string) => (await on.call('GET', `/api/docs/${docId}/markdown`)).body.blocks

async function agentReplace(on: TestService, docId: string, index: number, markdown: string) {
  const block = (await blocks(on, docId))[index]
  const response = await on.call('POST', `/api/docs/${docId}/edits`, {
    mandateId: 'm1',
    author: AGENT,
    ops: [{ op: 'replace', blockId: block.id, digest: block.digest, markdown }],
  })
  assert.equal(response.status, 200, JSON.stringify(response.body))
  return response.body
}

async function editor(on: TestService, docId: string, uid: string) {
  const c = client(on.ws, docId, token(uid, 'editor', docId))
  await waitFor(() => c.synced)
  return c
}

test('a new document has its first version, announced to the host with the secret', async () => {
  await createDoc(service, 'd_first')
  const [first] = await versionsOf(service, 'd_first')
  assert.deepEqual([first.reason, first.authors], ['created', [ALICE]])
  await waitFor(() => announced.some((a) => a.body.docId === 'd_first'))
  const call = announced.find((a) => a.body.docId === 'd_first')!
  assert.equal(call.secret, API_SECRET)
  assert.equal(call.body.id, first.id)
})

test("people's edits become one version after a quiet spell, with everyone who edited", async () => {
  await createDoc(service, 'd_idle')
  const bob = await editor(service, 'd_idle', 'u_bob')
  const carol = await editor(service, 'd_idle', 'u_carol')
  addParagraph(bob.ydoc, 'Bob was here.', { id: 'u_bob', kind: 'person' })
  addParagraph(carol.ydoc, 'Carol too.', { id: 'u_carol', kind: 'person' })
  await waitFor(async () => (await versionsOf(service, 'd_idle')).length === 2)
  const [idle] = await versionsOf(service, 'd_idle')
  assert.equal(idle.reason, 'idle')
  assert.deepEqual(idle.authors.map((a: any) => a.id).sort(), ['u_bob', 'u_carol'])
  bob.provider.destroy()
  carol.provider.destroy()
})

test("an agent batch is its own version; people's edits just before it get theirs first", async () => {
  const slow = await startTestService(undefined, { idleMs: 60000 })
  try {
    await createDoc(slow, 'd_agent')
    const bob = await editor(slow, 'd_agent', 'u_bob')
    addParagraph(bob.ydoc, 'Bob was here.', { id: 'u_bob', kind: 'person' })
    await waitFor(async () => (await slow.call('GET', '/api/docs/d_agent/markdown')).body.markdown.includes('Bob was here'))
    const result = await agentReplace(slow, 'd_agent', 1, 'We ship on Friday.')
    const listed = await versionsOf(slow, 'd_agent')
    assert.deepEqual(listed.map((v: any) => v.reason), ['agent_turn', 'idle', 'created'])
    assert.equal(result.versionId, listed[0].id)
    assert.deepEqual([listed[0].authors, listed[0].mandateId], [[AGENT], 'm1'])
    assert.deepEqual(listed[1].authors, [BOB])
    bob.provider.destroy()
  } finally {
    await slow.stop()
  }
})

test('unchanged content makes no version; a named version is kept anyway', async () => {
  await createDoc(service, 'd_same')
  const doc = await service.pool.read('d_same')
  assert.equal(service.versions.record('d_same', doc, { reason: 'idle', authors: [] }), null)
  const named = await service.call('POST', '/api/docs/d_same/versions', { author: BOB, label: '  Before review ' })
  assert.equal(named.status, 200)
  assert.deepEqual([named.body.version.reason, named.body.version.label, named.body.version.authors], ['manual', 'Before review', [BOB]])
  assert.equal((await versionsOf(service, 'd_same')).length, 2)
})

test('the diff finds changed, added, removed and moved blocks, with the changed words', () => {
  const from = importDoc('# Plan\n\nAlpha one.\n\nBeta two.\n\nGamma three.\n\nDelta four.\n')
  const json: any = from.toJSON()
  const [heading, alpha, , gamma, delta] = json.content
  const revised = { ...alpha, content: [{ type: 'text', text: 'Alpha one, revised.' }] }
  const added = { type: 'paragraph', attrs: { id: 'b_new' }, content: [{ type: 'text', text: 'Epsilon five.' }] }
  const to = blackboardSchema().nodeFromJSON({ ...json, content: [heading, revised, delta, gamma, added] })
  const diff = diffDocs(from, to)
  const status = (id: string) => diff.blocks.find((b) => b.id === id)?.status
  assert.equal(status(heading.attrs.id), 'unchanged')
  assert.equal(status(alpha.attrs.id), 'changed')
  assert.equal(status('b_new'), 'added')
  assert.equal(diff.blocks.find((b) => b.status === 'removed')?.markdown, 'Beta two.')
  assert.equal([status(gamma.attrs.id), status(delta.attrs.id)].filter((s) => s === 'moved').length, 1)
  assert.deepEqual(diff.summary, { unchanged: 2, changed: 1, added: 1, removed: 1, moved: 1 })
  const inline = diff.blocks.find((b) => b.id === alpha.attrs.id)!.inline!
  assert.deepEqual(inline.filter((p) => p.op !== 'eq').map((p) => [p.op, p.text]), [['ins', ', revised']])
  // Against nothing, every block is new.
  assert.equal(diffDocs(null, to).summary.added, 5)
})

test('over HTTP the diff defaults to the previous version and shows a suggestion as its change', async () => {
  await createDoc(service, 'd_diff')
  const { versionId } = await agentReplace(service, 'd_diff', 1, 'We ship on Friday.')
  const diff = (await service.call('GET', `/api/docs/d_diff/diff?to=${versionId}`)).body
  const [created] = (await versionsOf(service, 'd_diff')).slice(-1)
  assert.equal(diff.from, created.id)
  const changed = diff.blocks.find((b: any) => b.status === 'changed')
  assert.deepEqual([changed.pending, changed.wasPending], [true, false])
  assert.ok(changed.inline.some((p: any) => p.op === 'ins' && p.text.includes('Friday')))
  assert.equal((await service.call('GET', '/api/docs/d_diff/diff?to=nope')).status, 404)
})

test('restore brings a version back with its suggestions pending, as a new version', async () => {
  await createDoc(service, 'd_restore')
  const { versionId } = await agentReplace(service, 'd_restore', 1, 'We ship on Friday.')
  const imported = await service.call('POST', '/api/docs/d_restore/import', { markdown: '# Other\n\nNothing left.\n', author: BOB })
  assert.equal(imported.status, 200)
  assert.equal((await versionsOf(service, 'd_restore'))[0].reason, 'import')
  assert.deepEqual((await versionsOf(service, 'd_restore'))[0].authors, [BOB])

  const restored = await service.call('POST', '/api/docs/d_restore/restore', { versionId, author: BOB })
  assert.equal(restored.status, 200)
  assert.deepEqual([restored.body.version.reason, restored.body.version.restoredFrom], ['restore', versionId])
  const proposed = (await service.call('GET', '/api/docs/d_restore/markdown?view=proposed')).body.markdown
  assert.match(proposed, /We ship on Friday\./)
  const suggestions = (await service.call('GET', '/api/docs/d_restore/suggestions')).body.suggestions
  assert.ok(suggestions.length > 0 && suggestions.every((s: any) => s.author.mandate === 'm1'))
  const markdown = (await service.call('GET', `/api/docs/d_restore/versions/${versionId}?format=markdown`)).body.markdown
  assert.match(markdown, /We ship once the tests pass\./)
})

test('Markdown and Word exports leave pending suggestions out and append the decisions', async () => {
  await createDoc(service, 'd_export', `${DOC}\n- one\n- two\n\n| A | B |\n| --- | --- |\n| 1 | 2 |\n`)
  await agentReplace(service, 'd_export', 1, 'We ship on Friday.')
  const decisions = [{ question: 'Which risks?', answer: 'Quality', answeredBy: 'Alice', acceptedBy: 'Bob' }]
  const md = await service.call('POST', '/api/docs/d_export/export', { format: 'md', title: 'Launch: plan', decisions })
  assert.equal(md.status, 200)
  assert.equal(md.body.fileName, 'Launch plan.md')
  const text = Buffer.from(md.body.data, 'base64').toString('utf8')
  assert.match(text, /We ship once the tests pass\./)
  assert.doesNotMatch(text, /Friday/)
  assert.match(text, /## Decisions/)
  assert.match(text, /\| Which risks\? \| Quality \| Alice \| Bob \|/)

  const docx = await service.call('POST', '/api/docs/d_export/export', { format: 'docx', title: 'Launch plan', decisions })
  assert.equal(docx.status, 200)
  assert.equal(docx.body.contentType, 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
  const zip = await JSZip.loadAsync(Buffer.from(docx.body.data, 'base64'))
  const xml = await zip.file('word/document.xml')!.async('string')
  // Marks split a sentence into several runs; the text is read without the markup.
  const words = xml.replace(/<\/w:p>/g, '\n').replace(/<[^>]+>/g, '')
  for (const expected of ['Launch plan', 'We ship once the tests pass.', 'Second paragraph.', 'Decisions', 'Quality']) assert.ok(words.includes(expected), expected)
  assert.ok(!words.includes('Friday'))
  assert.equal((xml.match(/<w:tbl>/g) ?? []).length, 2)

  assert.equal((await service.call('POST', '/api/docs/d_export/export', { format: 'odt' })).body.code, 'unsupported_format')
})

test('PDF export prints with a local browser, or says that none was found', async () => {
  await createDoc(service, 'd_pdf')
  const response = await service.call('POST', '/api/docs/d_pdf/export', { format: 'pdf', title: 'Plan' })
  if (!findChromium(null)) {
    assert.deepEqual([response.status, response.body.code], [409, 'pdf_unavailable'])
    return
  }
  assert.equal(response.status, 200, JSON.stringify(response.body))
  const pdf = Buffer.from(response.body.data, 'base64')
  assert.equal(pdf.subarray(0, 5).toString('ascii'), '%PDF-')
  assert.ok((pdf.toString('latin1').match(/\/Type\s*\/Page[^s]/g) ?? []).length >= 1)
})

test('image sizes come from the file header', () => {
  const png = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAIAAAADCAYAAAC56t6BAAAAEklEQVR4nGNgYGD4z8DAwMAAAAQHAQE1K0wAAAAASUVORK5CYII=', 'base64')
  assert.deepEqual(pictureOf(png) && { type: pictureOf(png)!.type, width: pictureOf(png)!.width, height: pictureOf(png)!.height }, { type: 'png', width: 2, height: 3 })
  assert.equal(pictureOf(Buffer.from('not an image')), null)
})
