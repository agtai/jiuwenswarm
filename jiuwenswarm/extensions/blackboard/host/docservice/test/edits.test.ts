// The edits endpoint: compare-and-set, scope, all or nothing, suggestions with the agent as author,
// the attribution pass, and deciding suggestions (spike 5 cases, now against the real service).
import assert from 'node:assert/strict'
import { after, before, test } from 'node:test'
import { EditError, planEdit, type EditOp, type EditRequest } from '../src/docs/edits.ts'
import { agentView, blocksOf, importDoc } from '../src/docs/markdown.ts'
import { suggestionsIn } from '../src/docs/suggestions.ts'
import { addParagraph, client, startTestService, token, waitFor, type TestService } from './helpers.ts'

const ALICE = { id: 'u_alice', kind: 'person' }
const AGENT = (mandate: string) => ({ id: 'u_alice', kind: 'agent' as const, mandate })
let service: TestService

before(async () => {
  service = await startTestService()
})

after(async () => {
  await service.stop()
})

const request = (ops: EditOp[], mandate = 'm1', extra: Partial<EditRequest> = {}): EditRequest => ({
  mandateId: mandate,
  author: AGENT(mandate),
  mode: 'suggest',
  ops,
  ...extra,
})

function fails(code: string, fn: () => unknown): EditError {
  try {
    fn()
  } catch (error) {
    assert.ok(error instanceof EditError, String(error))
    assert.equal(error.code, code)
    return error
  }
  throw new Error(`expected ${code}`)
}

const DOC = '# Plan\n\nWe ship once the tests pass.\n\nSecond paragraph.\n\nThird paragraph.\n'

test('a same-type replace suggests only the changed words and keeps the block id', () => {
  const doc = importDoc(DOC)
  const [, p1] = blocksOf(doc)
  const { doc: next, result } = planEdit(doc, request([{ op: 'replace', blockId: p1.id!, digest: p1.digest, markdown: 'We ship one day after the tests pass.' }]))
  assert.equal(result.changed, true)
  assert.equal(result.suggestionIds.length > 0, true)
  const after = blocksOf(next)
  assert.equal(after[1].id, p1.id)
  const suggestions = suggestionsIn(next)
  // One replacement of whole words: "once" by "one day after", not "onc|e".
  assert.deepEqual(suggestions.map((s) => [s.deleted, s.inserted]), [['once', 'one day after']])
  for (const s of suggestions) assert.deepEqual(s.author, { id: 'u_alice', kind: 'agent', mandate: 'm1' })
  // The new words carry the agent's author mark too, so they stay credited after acceptance.
  let marked = ''
  next.descendants((node) => {
    if (node.isText && node.marks.some((m) => m.type.name === 'author' && m.attrs.kind === 'agent')) marked += node.text
  })
  assert.equal(marked, 'one day after')
  assert.equal(result.before[0].markdown, 'We ship once the tests pass.')
  assert.equal(result.after[0].id, p1.id)
})

test('a list replaced as a suggestion changes only its changed items, and both views read right', () => {
  // Each of these crashed the views before (an item cut in half by a diff across items).
  const cases = [
    ['- a one\n- b two', '- a one\n- b two\n- c three'],
    ['- a one\n- b two', '- a one\n- b two changed'],
    ['- a one\n- b two', '- a one more\n- b two more'],
    ['- a one\n- b two\n- c three', '- a one\n- c three'],
    ['1. a one\n2. b two', '1. a one\n2. b two\n3. c three'],
    ['> a one\n>\n> b two', '> a one\n>\n> b two\n>\n> c three'],
  ]
  for (const [old, wanted] of cases) {
    const doc = importDoc(`## H\n\n${old}\n`)
    const list = blocksOf(doc)[1]
    const { doc: next, result } = planEdit(doc, request([{ op: 'replace', blockId: list.id!, digest: list.digest, markdown: wanted }]))
    assert.equal(result.changed, true, wanted)
    const [, after] = blocksOf(next)
    assert.equal(after.id, list.id, wanted)
    assert.equal(after.markdown, list.markdown, `accepted view of ${wanted}`)
    assert.ok(agentView(next, { view: 'proposed' }).markdown.includes(blocksOf(importDoc(wanted))[0].markdown), `proposed view of ${wanted}`)
    // The first item did not change: it keeps its id and has no suggestion.
    assert.equal(next.child(1).child(0).attrs.id, doc.child(1).child(0).attrs.id, wanted)
  }
})

test('inserts keep the order of the ops and get fresh ids; delete marks the block', () => {
  const doc = importDoc(DOC)
  const [, p1, p2] = blocksOf(doc)
  const { doc: next, result } = planEdit(
    doc,
    request([
      { op: 'insert_after', blockId: p1.id!, markdown: 'First new.' },
      { op: 'insert_after', blockId: p1.id!, markdown: 'Second new.\n\nThird new.' },
      { op: 'delete', blockId: p2.id!, digest: p2.digest },
    ]),
  )
  const proposed = blocksOf(next).map((b) => b.id)
  const ids = result.after.map((b) => b.id)
  assert.equal(new Set(proposed).size, proposed.length)
  // The accepted view still has the deleted paragraph and not the insertions.
  assert.deepEqual(blocksOf(next).map((b) => b.markdown), ['# Plan', 'We ship once the tests pass.', '', '', '', 'Second paragraph.', 'Third paragraph.'])
  // One suggestion per op: accepting it takes all the blocks the op inserted.
  assert.deepEqual(
    suggestionsIn(next).map((s) => [s.inserted, s.deleted]),
    [['First new.', ''], ['Second new.Third new.', ''], ['', 'Second paragraph.']],
  )
  assert.ok(ids.includes(p1.id) && ids.includes(p2.id) && ids.length === 5)
})

test('a stale digest refuses the whole batch and returns the current text', () => {
  const doc = importDoc(DOC)
  const [, p1, p2] = blocksOf(doc)
  const error = fails('stale', () =>
    planEdit(
      doc,
      request([
        { op: 'replace', blockId: p1.id!, digest: p1.digest, markdown: 'Fine.' },
        { op: 'replace', blockId: p2.id!, digest: 'old', markdown: 'Stale.' },
      ]),
    ),
  )
  assert.deepEqual(error.details.changed_blocks, [{ id: p2.id, digest: p2.digest, markdown: 'Second paragraph.' }])
})

test('unknown blocks, the scope and unparseable Markdown are refused', () => {
  const doc = importDoc(DOC)
  const [h, p1, p2, p3] = blocksOf(doc)
  fails('unknown_block', () => planEdit(doc, request([{ op: 'delete', blockId: 'nope', digest: 'x' }])))
  const scoped = request([{ op: 'replace', blockId: p3.id!, digest: p3.digest, markdown: 'Out.' }], 'm1', {
    allowed: { blockFrom: p1.id!, blockTo: p2.id! },
  })
  assert.deepEqual(fails('out_of_scope', () => planEdit(doc, scoped)).details.block_ids, [p3.id])
  fails('unsupported_markdown', () => planEdit(doc, request([{ op: 'insert_after', blockId: h.id!, markdown: '' }])))
  fails('invalid', () =>
    planEdit(
      doc,
      request([
        { op: 'delete', blockId: p1.id!, digest: p1.digest },
        { op: 'replace', blockId: p1.id!, digest: p1.digest, markdown: 'Twice.' },
      ]),
    ),
  )
})

test("another mandate's pending suggestion blocks a rewrite; its own is revised; neighbours keep their ids", () => {
  let doc = importDoc(DOC)
  const [, p1] = blocksOf(doc)
  doc = planEdit(doc, request([{ op: 'replace', blockId: p1.id!, digest: p1.digest, markdown: 'We ship on Friday.' }], 'm1')).doc
  const first = suggestionsIn(doc).map((s) => s.id)
  const p1now = blocksOf(doc)[1]

  const error = fails('pending_suggestions', () =>
    planEdit(doc, request([{ op: 'replace', blockId: p1now.id!, digest: p1now.digest, markdown: 'Other.' }], 'm2')),
  )
  assert.deepEqual(
    (error.details.suggestions as any[]).map((s) => s.author.mandate),
    first.map(() => 'm1'),
  )

  // m2 may insert next to m1's suggestion; both keep their own ids and authors.
  const beside = planEdit(doc, request([{ op: 'insert_after', blockId: p1now.id!, markdown: 'From m2.' }], 'm2')).doc
  const byMandate = new Map(suggestionsIn(beside).map((s) => [s.id, s.author?.mandate]))
  assert.ok(first.every((id) => byMandate.get(id) === 'm1'))
  assert.equal([...byMandate.values()].filter((m) => m === 'm2').length, 1)

  // m1 revises its own proposal: the old suggestion is reverted, the new text suggested.
  const revised = planEdit(doc, request([{ op: 'replace', blockId: p1now.id!, digest: p1now.digest, markdown: 'We ship on Monday.' }], 'm1')).doc
  const proposed = blocksOf(revised)[1]
  assert.equal(proposed.markdown, 'We ship once the tests pass.')
  assert.ok(suggestionsIn(revised).every((s) => !first.includes(s.id)))
  assert.ok(suggestionsIn(revised).some((s) => s.inserted.includes('Monday')))
})

test('direct mode writes plain text credited to the agent', () => {
  const doc = importDoc(DOC)
  const [, , p2] = blocksOf(doc)
  const { doc: next, result } = planEdit(doc, request([{ op: 'replace', blockId: p2.id!, digest: p2.digest, markdown: 'Rewritten directly.' }], 'm1', { mode: 'direct' }))
  assert.deepEqual(result.suggestionIds, [])
  assert.equal(blocksOf(next)[2].markdown, 'Rewritten directly.')
  assert.deepEqual(suggestionsIn(next), [])
})

async function createDoc(docId: string, markdown = DOC) {
  const response = await service.call('POST', '/api/docs', { docId, markdown, author: ALICE })
  assert.equal(response.status, 200)
}

const view = async (docId: string, which = 'accepted') => (await service.call('GET', `/api/docs/${docId}/markdown?view=${which}`)).body

test('over HTTP: saved before the reply, two batches on one block race to one winner, errors are 409', async () => {
  await createDoc('d_http')
  const { blocks } = await view('d_http')
  const p1 = blocks[1]
  const edit = (markdown: string) =>
    service.call('POST', '/api/docs/d_http/edits', {
      mandateId: 'm1',
      author: { id: 'u_alice', kind: 'agent' },
      ops: [{ op: 'replace', blockId: p1.id, digest: p1.digest, markdown }],
    })
  const [a, b] = await Promise.all([edit('We ship on Friday.'), edit('We ship on Sunday.')])
  assert.deepEqual([a.status, b.status].sort(), [200, 409])
  const loser = a.status === 409 ? a : b
  assert.equal(loser.body.code, 'stale')
  assert.match((await view('d_http', 'proposed')).markdown, /We ship on (Friday|Sunday)\./)
  // Saved before the reply: the SQLite row already has it.
  assert.ok(service.storage.fetch('d_http'))

  const person = await service.call('POST', '/api/docs/d_http/edits', { author: ALICE, ops: [{ op: 'delete', blockId: p1.id, digest: 'x' }] })
  assert.equal(person.status, 400)
})

test('accept keeps the agent as author; reject restores the text; the list names blocks', async () => {
  await createDoc('d_decide')
  const { blocks } = await view('d_decide')
  const [, p1, p2] = blocks
  const agent = { id: 'u_alice', kind: 'agent' }
  await service.call('POST', '/api/docs/d_decide/edits', {
    mandateId: 'm1',
    author: agent,
    ops: [
      { op: 'replace', blockId: p1.id, digest: p1.digest, markdown: 'We ship on Friday.' },
      { op: 'replace', blockId: p2.id, digest: p2.digest, markdown: 'Second paragraph, revised.' },
    ],
  })
  const listed = (await service.call('GET', '/api/docs/d_decide/suggestions')).body.suggestions
  assert.ok(listed.length >= 2)
  assert.ok(listed.every((s: any) => s.author.mandate === 'm1' && s.blockIds.length === 1))
  for (const s of listed.filter((x: any) => x.blockIds[0] === p1.id)) {
    assert.equal((await service.call('POST', `/api/docs/d_decide/suggestions/${s.id}`, { action: 'accept' })).status, 200)
  }
  for (const s of listed.filter((x: any) => x.blockIds[0] === p2.id)) {
    assert.equal((await service.call('POST', `/api/docs/d_decide/suggestions/${s.id}`, { action: 'reject' })).status, 200)
  }
  const accepted = await view('d_decide')
  assert.match(accepted.markdown, /We ship on Friday\./)
  assert.match(accepted.markdown, /\nSecond paragraph\.\n/)
  assert.ok(accepted.blocks.every((b: any) => !b.hasPendingSuggestions))
  const missing = await service.call('POST', '/api/docs/d_decide/suggestions/snope', { action: 'accept' })
  assert.equal(missing.status, 404)
})

test("a batch lands while a person edits another block; the agent's caret appears and goes", async () => {
  await createDoc('d_live')
  const bob = client(service.ws, 'd_live', token('u_bob', 'editor', 'd_live'))
  try {
    await waitFor(() => bob.synced)
    addParagraph(bob.ydoc, 'Bob types at the end.', { id: 'u_bob', kind: 'person' })
    const { blocks } = await view('d_live')
    const p1 = blocks[1]
    const edit = await service.call('POST', '/api/docs/d_live/edits', {
      mandateId: 'm1',
      author: { id: 'u_alice', kind: 'agent' },
      ops: [{ op: 'replace', blockId: p1.id, digest: p1.digest, markdown: 'We ship on Friday.' }],
    })
    assert.equal(edit.status, 200)
    await waitFor(async () => /Bob types at the end\./.test((await view('d_live')).markdown))
    assert.match((await view('d_live', 'proposed')).markdown, /We ship on Friday\./)

    const shown = await service.call('POST', '/api/docs/d_live/presence', { agentId: 'u_alice', label: "Alice's agent", status: 'writing', blockId: p1.id })
    assert.equal(shown.body.shown, true)
    const agentState = () => [...bob.provider.awareness!.getStates().values()].find((s: any) => s.user?.kind === 'agent') as any
    await waitFor(() => Boolean(agentState()))
    assert.equal(agentState().user.name, "Alice's agent")
    assert.ok(agentState().cursor?.anchor)
    await service.call('POST', '/api/docs/d_live/presence', { status: null })
    await waitFor(() => !agentState())
  } finally {
    bob.provider.destroy()
  }
})
