import assert from 'node:assert/strict'
import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'
import test from 'node:test'
import { Fragment } from '@tiptap/pm/model'
import { blackboardSchema } from '../src/schema/extensions.ts'
import { agentView, blocksOf, hasRawHtml, importDoc, parseMarkdown, serializeBlock, serializeMarkdown } from '../src/docs/markdown.ts'
import { stripIds } from './helpers.ts'

const CORPUS = join(import.meta.dirname, 'corpus')
const files = readdirSync(CORPUS).filter((f) => f.endsWith('.md')).sort()

test('the corpus has the spike 1 files', () => {
  assert.equal(files.length, 20)
})

for (const file of files) {
  test(`round trip: ${file}`, () => {
    const source = readFileSync(join(CORPUS, file), 'utf8')
    const first = importDoc(source)
    const markdown = serializeMarkdown(first.toJSON())
    const second = importDoc(markdown)
    // Parse, serialize, parse gives the same tree, and the serializer reaches a fixed point.
    assert.deepEqual(stripIds(second.toJSON()), stripIds(first.toJSON()))
    assert.equal(serializeMarkdown(second.toJSON()), markdown)
    // Every top-level block serialized alone parses back to the same single block.
    first.forEach((block) => {
      const alone = parseMarkdown(serializeBlock(block.toJSON() as any))
      if (block.type.name === 'paragraph' && !block.content.size) return
      assert.equal(alone.content?.length, 1, `${file}: ${block.type.name}`)
      const parsed = blackboardSchema().nodeFromJSON(alone.content![0]).toJSON()
      assert.deepEqual(stripIds(parsed), stripIds(block.toJSON()))
    })
  })
}

test('the agent view names every top-level block, and digests are stable across imports', () => {
  const doc = importDoc(readFileSync(join(CORPUS, '17-launch-plan.md'), 'utf8'))
  const view = agentView(doc)
  const ids: string[] = []
  doc.forEach((node) => ids.push(node.attrs.id))
  assert.equal(view.blocks.length, doc.childCount)
  for (const id of ids) assert.ok(view.markdown.includes(`<!-- block:${id} -->`), id)
  const again = blocksOf(importDoc(serializeMarkdown(doc.toJSON())))
  assert.deepEqual(again.map((b) => b.digest), view.blocks.map((b) => b.digest))
})

test('a pending suggestion changes the digest but not the accepted view', () => {
  const schema = blackboardSchema()
  const doc = importDoc('First paragraph.\n\nSecond paragraph.\n')
  const before = blocksOf(doc)
  const second = doc.child(1)
  const insertion = schema.marks.insertion.create({ id: 's1', author: { id: 'jiuwen', kind: 'agent' } })
  const suggested = second.copy(second.content.append(Fragment.from(schema.text(' More.', [insertion]))))
  const changed = doc.copy(Fragment.from([doc.child(0), suggested]))
  const after = blocksOf(changed)
  assert.equal(after[1].markdown, before[1].markdown)
  assert.equal(after[1].hasPendingSuggestions, true)
  assert.notEqual(after[1].digest, before[1].digest)
  assert.equal(after[0].digest, before[0].digest)
  assert.match(agentView(changed, { view: 'proposed' }).markdown, /Second paragraph\. More\./)
})

test('a range limits the agent view to contiguous blocks', () => {
  const doc = importDoc('# One\n\nTwo\n\nThree\n\nFour\n')
  const ids: string[] = []
  doc.forEach((node) => ids.push(node.attrs.id))
  const view = agentView(doc, { range: `${ids[1]}..${ids[2]}` })
  assert.deepEqual(view.blocks.map((b) => b.id), [ids[1], ids[2]])
  assert.throws(() => agentView(doc, { range: `${ids[2]}..${ids[1]}` }), /range/)
})

test('an empty document imports as one empty paragraph and raw HTML is flagged', () => {
  const doc = importDoc('')
  assert.equal(doc.childCount, 1)
  assert.match(agentView(doc).markdown, /&nbsp;/)
  assert.equal(hasRawHtml('Hello <span>there</span>'), true)
  assert.equal(hasRawHtml('Line one<br>line two'), false)
})

test('a 100 KB document parses in well under two seconds', () => {
  const block = readFileSync(join(CORPUS, '16-meeting-notes.md'), 'utf8')
  let markdown = ''
  while (markdown.length < 100_000) markdown += block + '\n\n'
  const started = performance.now()
  const doc = importDoc(markdown)
  const elapsed = performance.now() - started
  assert.ok(doc.childCount > 100)
  assert.ok(elapsed < 2000, `took ${Math.round(elapsed)} ms`)
})
