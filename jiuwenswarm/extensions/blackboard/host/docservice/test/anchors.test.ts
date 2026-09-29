// Comment anchors against a live Y.Doc: unchanged, edited before, edited inside, block moved, block
// deleted, quote duplicated, and a passage over two blocks; then through the HTTP route.
import assert from 'node:assert/strict'
import { after, before, test } from 'node:test'
import type { Node as PMNode } from '@tiptap/pm/model'
import { EditorState } from '@tiptap/pm/state'
import * as Y from 'yjs'
import { absolutePositionToRelativePosition, initProseMirrorDoc } from '../vendor/y-tiptap-nodemarks.js'
import { encode, resolveAnchors, SEPARATOR, type Anchor } from '../src/docs/anchors.ts'
import { blockInfo, importDoc } from '../src/docs/markdown.ts'
import { FIELD, readDoc, writeDoc } from '../src/docs/pool.ts'
import { blackboardSchema } from '../src/schema/extensions.ts'
import { startTestService, type TestService } from './helpers.ts'

const DOC = '# Plan\n\nWe ship the product once the tests pass.\n\nSecond paragraph about risks.\n\nThird paragraph.\n'

function load(markdown: string): Y.Doc {
  const ydoc = new Y.Doc()
  writeDoc(ydoc, importDoc(markdown))
  return ydoc
}

// The range of `text` in the document, which must occur once.
function find(doc: PMNode, text: string): { from: number; to: number } {
  let found: { from: number; to: number } | null = null
  doc.descendants((node, pos) => {
    if (node.isText && node.text!.includes(text)) found = { from: pos + node.text!.indexOf(text), to: pos + node.text!.indexOf(text) + text.length }
  })
  assert.ok(found, `${text} is not in the document`)
  return found!
}

// What the browser sends for a selection from `from` to `to`.
function anchorFor(ydoc: Y.Doc, from: number, to: number): Anchor {
  const fragment = ydoc.getXmlFragment(FIELD)
  const { doc, mapping } = initProseMirrorDoc(fragment, blackboardSchema()) as { doc: PMNode; mapping: Map<any, any> }
  const block = doc.resolve(from).node(1)
  const last = doc.resolve(to).node(1)
  return {
    block_id: block.attrs.id,
    block_to: last.attrs.id,
    digest: blockInfo(block).digest,
    start: encode(absolutePositionToRelativePosition(from, fragment, mapping)),
    end: encode(absolutePositionToRelativePosition(to, fragment, mapping)),
    quote: doc.textBetween(from, to, SEPARATOR),
  }
}

function change(ydoc: Y.Doc, edit: (state: EditorState) => EditorState['tr']): void {
  const state = EditorState.create({ doc: readDoc(ydoc) })
  writeDoc(ydoc, edit(state).doc)
}

function selection(ydoc: Y.Doc, text: string): Anchor {
  const { from, to } = find(readDoc(ydoc), text)
  return anchorFor(ydoc, from, to)
}

test('an untouched passage resolves where it was', () => {
  const ydoc = load(DOC)
  const anchor = selection(ydoc, 'once the tests pass')
  const [resolved] = resolveAnchors(ydoc, [anchor])
  assert.equal(resolved.status, 'ok')
  assert.deepEqual(find(readDoc(ydoc), 'once the tests pass'), { from: resolved.from, to: resolved.to })
  assert.equal(resolved.block_id, anchor.block_id)
})

test('text added before the passage moves it along', () => {
  const ydoc = load(DOC)
  const anchor = selection(ydoc, 'once the tests pass')
  change(ydoc, (state) => state.tr.insertText('Finally, ', find(state.doc, 'We ship').from))
  const [resolved] = resolveAnchors(ydoc, [anchor])
  assert.equal(resolved.status, 'ok')
  assert.deepEqual({ from: resolved.from, to: resolved.to }, find(readDoc(ydoc), 'once the tests pass'))
})

test('an edit inside the passage makes it drifted, still in place', () => {
  const ydoc = load(DOC)
  const anchor = selection(ydoc, 'once the tests pass')
  change(ydoc, (state) => {
    const { from, to } = find(state.doc, 'tests')
    return state.tr.insertText('checks', from, to)
  })
  const [resolved] = resolveAnchors(ydoc, [anchor])
  assert.equal(resolved.status, 'drifted')
  assert.equal(resolved.quote_now, 'once the checks pass')
})

test('a pending suggestion inside the passage leaves it as it was', () => {
  const ydoc = load(DOC)
  const anchor = selection(ydoc, 'once the tests pass')
  change(ydoc, (state) => {
    const { from, to } = find(state.doc, 'tests')
    const author = { id: 'jiuwen', kind: 'agent' }
    const { insertion, deletion } = state.schema.marks
    return state.tr
      .addMark(from, to, deletion.create({ id: 's1', author }))
      .insert(to, state.schema.text('checks', [insertion.create({ id: 's1', author })]))
  })
  const [resolved] = resolveAnchors(ydoc, [anchor])
  assert.equal(resolved.status, 'ok')
  assert.equal(resolved.quote_now, 'once the tests pass')
})

test('a moved paragraph is found again by its text and the anchor follows it', () => {
  const ydoc = load(DOC)
  const anchor = selection(ydoc, 'about risks')
  change(ydoc, (state) => {
    const doc = state.doc
    let start = 0
    let node: PMNode | null = null
    doc.forEach((child, pos) => {
      if (child.textContent.startsWith('Second')) {
        start = pos
        node = child
      }
    })
    const copy = blackboardSchema().nodeFromJSON({ ...node!.toJSON(), attrs: { ...node!.attrs, id: 'b_moved' } })
    return state.tr.delete(start, start + node!.nodeSize).insert(doc.content.size - node!.nodeSize, copy)
  })
  const [resolved] = resolveAnchors(ydoc, [anchor])
  assert.equal(resolved.status, 'ok')
  assert.equal(resolved.block_id, 'b_moved')
  assert.deepEqual({ from: resolved.from, to: resolved.to }, find(readDoc(ydoc), 'about risks'))
  // The new positions hold the passage from now on.
  const [again] = resolveAnchors(ydoc, [{ ...anchor, start: resolved.start!, end: resolved.end!, block_id: 'b_moved' }])
  assert.deepEqual({ status: again.status, from: again.from }, { status: 'ok', from: resolved.from })
})

test('a deleted paragraph orphans its passage, and so does a quote found twice', () => {
  const ydoc = load(DOC)
  const gone = selection(ydoc, 'Second paragraph')
  const twice = selection(ydoc, 'about risks')
  change(ydoc, (state) => {
    let tr = state.tr
    state.doc.forEach((child, pos) => {
      if (child.textContent.startsWith('Second')) tr = tr.delete(pos, pos + child.nodeSize)
    })
    return tr
  })
  change(ydoc, (state) => state.tr.insertText(' Notes about risks, and more about risks.', find(state.doc, 'Third paragraph.').to))
  const [first, second] = resolveAnchors(ydoc, [gone, twice])
  assert.equal(first.status, 'orphaned')
  assert.equal(second.status, 'orphaned')
})

test('a passage over two paragraphs keeps both ends', () => {
  const ydoc = load(DOC)
  const doc = readDoc(ydoc)
  const anchor = anchorFor(ydoc, find(doc, 'tests pass').from, find(doc, 'Second').to)
  assert.equal(anchor.quote, `tests pass.${SEPARATOR}Second`)
  const [resolved] = resolveAnchors(ydoc, [anchor])
  assert.equal(resolved.status, 'ok')
  assert.notEqual(resolved.block_id, resolved.block_to)
})

let service: TestService

before(async () => {
  service = await startTestService()
})

after(async () => {
  await service.stop()
})

test('the route resolves anchors of a stored document', async () => {
  await service.call('POST', '/api/docs', { docId: 'd_anchor', markdown: DOC, author: { id: 'u_alice', kind: 'person' } })
  // Positions that point nowhere: the quote alone decides.
  const junk = { block_id: 'b_x', start: 'AAAA', end: 'AAAA', quote: 'no such words anywhere' }
  const found = { block_id: 'b_x', start: 'AAAA', end: 'AAAA', quote: 'Third paragraph' }
  const response = await service.call('POST', '/api/docs/d_anchor/anchors/resolve', { anchors: [junk, found] })
  assert.equal(response.status, 200)
  const [missing, moved] = response.body.anchors
  assert.equal(missing.status, 'orphaned')
  assert.equal(moved.status, 'ok')
  assert.ok(moved.start && moved.end && moved.block_id)
  const bad = await service.call('POST', '/api/docs/d_anchor/anchors/resolve', { anchors: 'nope' })
  assert.equal(bad.status, 400)
})
