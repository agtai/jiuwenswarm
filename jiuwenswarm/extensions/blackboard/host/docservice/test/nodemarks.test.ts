// Whole-block suggestions are node marks; stock y-tiptap drops them (spike 2), the vendored copy keeps them.
import assert from 'node:assert/strict'
import { spawnSync } from 'node:child_process'
import { join } from 'node:path'
import test from 'node:test'
import * as Y from 'yjs'
import * as stock from '@tiptap/y-tiptap'
import { blackboardSchema } from '../src/schema/extensions.ts'
import { importDoc } from '../src/docs/markdown.ts'
import { readDoc, writeDoc } from '../src/docs/pool.ts'

function docWithBlockInsertion() {
  const schema = blackboardSchema()
  const doc = importDoc('Kept paragraph.\n\nSuggested paragraph.\n')
  const mark = schema.marks.insertion.create({ id: 's_block', author: { id: 'jiuwen', kind: 'agent', mandate: 'm1' } })
  const second = doc.child(1).mark([mark])
  return doc.copy(doc.content.replaceChild(1, second))
}

test('a block-level suggestion survives the trip through Yjs', () => {
  const ydoc = new Y.Doc()
  writeDoc(ydoc, docWithBlockInsertion())
  const copy = new Y.Doc()
  Y.applyUpdate(copy, Y.encodeStateAsUpdate(ydoc))
  const back = readDoc(copy)
  const marks = back.child(1).marks.map((m) => ({ type: m.type.name, attrs: { ...m.attrs } }))
  assert.deepEqual(marks, [{ type: 'insertion', attrs: { id: 's_block', author: { id: 'jiuwen', kind: 'agent', mandate: 'm1' } } }])
  assert.equal(back.child(0).marks.length, 0)
})

test('stock y-tiptap drops it, which is why the patch exists', () => {
  const ydoc = new Y.Doc()
  const fragment = ydoc.getXmlFragment('default')
  ydoc.transact(() => stock.updateYFragment(ydoc, fragment, docWithBlockInsertion(), { mapping: new Map(), isOMark: new Map() } as any))
  const back = stock.yXmlFragmentToProseMirrorRootNode(fragment, blackboardSchema())
  assert.equal(back.child(1).marks.length, 0)
})

test('the vendored copy matches a fresh patch of the pinned y-tiptap', () => {
  const script = join(import.meta.dirname, '..', 'scripts', 'make-ytiptap-nodemarks.mjs')
  const result = spawnSync(process.execPath, [script, '--check'], { encoding: 'utf8' })
  assert.equal(result.status, 0, result.stderr)
})
