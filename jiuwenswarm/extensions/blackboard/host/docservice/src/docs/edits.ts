// An agent's batch of block operations (POST /api/docs/:id/edits). The batch is checked as a whole
// and becomes one change, suggestions by the agent in 'suggest' mode, or nothing is written at all.
import { revertSuggestion } from '@handlewithcare/prosemirror-suggest-changes'
import { Fragment, type Node as PMNode } from '@tiptap/pm/model'
import { EditorState, type Transaction } from '@tiptap/pm/state'
import { blackboardSchema } from '../schema/extensions.ts'
import { assignFreshIds, blockInfo, parseMarkdown, type Block } from './markdown.ts'
import { suggestAttributed, suggestionsIn, type Author } from './suggestions.ts'

export const MAX_OPS = 50
const OPS = ['replace', 'insert_after', 'insert_before', 'delete'] as const

export interface EditOp {
  op: (typeof OPS)[number]
  blockId: string
  digest?: string
  markdown?: string
}

export interface EditRequest {
  mandateId: string | null
  author: Author
  mode: 'suggest' | 'direct'
  // A block range the batch must stay in, inclusive; none means the whole document.
  allowed?: { blockFrom: string; blockTo: string } | null
  ops: EditOp[]
}

export interface BlockText {
  id: string | null
  digest: string
  markdown: string
}

export interface EditResult {
  changed: boolean
  suggestionIds: string[]
  // The touched blocks before, and the touched and new blocks after, in document order.
  before: BlockText[]
  after: BlockText[]
}

export class EditError extends Error {
  code: string
  details: Record<string, unknown>
  constructor(code: string, message: string, details: Record<string, unknown> = {}) {
    super(message)
    this.code = code
    this.details = details
  }
}

interface Located {
  node: PMNode
  index: number
  from: number
  to: number
}

function locate(doc: PMNode): Map<string, Located> {
  const out = new Map<string, Located>()
  doc.forEach((node, offset, index) => {
    if (node.attrs.id) out.set(node.attrs.id, { node, index, from: offset, to: offset + node.nodeSize })
  })
  return out
}

const text = (b: Block): BlockText => ({ id: b.id, digest: b.digest, markdown: b.markdown })

export function readOps(value: unknown): EditOp[] {
  if (!Array.isArray(value) || value.length === 0) throw new EditError('invalid', 'ops must be a non-empty list')
  if (value.length > MAX_OPS) throw new EditError('invalid', `a batch holds at most ${MAX_OPS} ops`)
  return value.map((raw, i) => {
    const op = raw as Partial<EditOp>
    if (!op || !OPS.includes(op.op as any)) throw new EditError('invalid', `op ${i}: op must be one of ${OPS.join(', ')}`, { op: i })
    if (typeof op.blockId !== 'string' || !op.blockId) throw new EditError('invalid', `op ${i}: blockId is required`, { op: i })
    if ((op.op === 'replace' || op.op === 'delete') && typeof op.digest !== 'string') {
      throw new EditError('invalid', `op ${i}: ${op.op} needs the digest from the last read`, { op: i })
    }
    if (op.op !== 'delete' && typeof op.markdown !== 'string') throw new EditError('invalid', `op ${i}: markdown is required`, { op: i })
    return { op: op.op as EditOp['op'], blockId: op.blockId, digest: op.digest, markdown: op.markdown }
  })
}

// New content from an op's Markdown: top-level blocks with fresh ids, every text carrying the
// agent's author mark.
function parseBlocks(markdown: string, opIndex: number, author: Author): PMNode[] {
  const schema = blackboardSchema()
  const json = assignFreshIds(parseMarkdown(markdown))
  const mark = schema.marks.author.create({ id: author.id, kind: author.kind, mandate: author.mandate ?? null }).toJSON()
  const stamp = (node: any): any => {
    if (node.type === 'text') return { ...node, marks: [...(node.marks || []).filter((m: any) => m.type !== 'author'), mark] }
    return node.content ? { ...node, content: node.content.map(stamp) } : node
  }
  const nodes: PMNode[] = []
  try {
    for (const block of json.content || []) {
      const node = schema.nodeFromJSON(stamp(block))
      node.check()
      nodes.push(node)
    }
  } catch (error) {
    throw new EditError('unsupported_markdown', `op ${opIndex}: the Markdown does not parse into valid blocks`, {
      op: opIndex,
      detail: error instanceof Error ? error.message : String(error),
    })
  }
  if (!nodes.length) throw new EditError('unsupported_markdown', `op ${opIndex}: the Markdown holds no block`, { op: opIndex })
  return nodes
}

const sameMarkup = (a: PMNode, b: PMNode) =>
  a.type === b.type && JSON.stringify({ ...a.attrs, id: null }) === JSON.stringify({ ...b.attrs, id: null })

const WORD = /[\p{L}\p{N}_]/u
function charAt(fragment: Fragment, pos: number): string {
  if (pos < 0 || pos >= fragment.size) return ''
  return fragment.textBetween(pos, pos + 1, ' ', ' ')
}
const isWord = (c: string) => c !== '' && WORD.test(c)

// Widen a changed range [start, endA) in `a` / [start, endB) in `b` to whole words, so "once" to
// "one" suggests the word and not "onc|e". Both sides share the text outside the range.
function snapToWords(a: Fragment, b: Fragment, start: number, endA: number, endB: number) {
  while (start > 0 && isWord(charAt(a, start - 1)) && (isWord(charAt(a, start)) || isWord(charAt(b, start)))) start--
  while (endA < a.size && endB < b.size && isWord(charAt(a, endA)) && (isWord(charAt(a, endA - 1)) || isWord(charAt(b, endB - 1)))) {
    endA++
    endB++
  }
  return { start, endA, endB }
}

// The same content without author marks, for comparing text written by different people.
function withoutAuthors(fragment: Fragment): Fragment {
  const nodes: PMNode[] = []
  fragment.forEach((node) => {
    const marks = node.marks.filter((m) => m.type.name !== 'author')
    nodes.push(node.isText ? node.mark(marks) : node.type.create(node.attrs, withoutAuthors(node.content), marks))
  })
  return Fragment.fromArray(nodes)
}

// Replace a block with one of the same type and attributes: only the changed words, so the
// suggestion shows what changed and the block keeps its id. The comparison ignores who wrote the
// old text; the new words come in with the agent's author mark.
function replaceInside(tr: Transaction, from: number, old: PMNode, replacement: PMNode): void {
  const next = old.type.create(old.attrs, replacement.content, old.marks)
  const a = withoutAuthors(old.content)
  const b = withoutAuthors(next.content)
  const start = a.findDiffStart(b)
  if (start == null) return
  const end = a.findDiffEnd(b)!
  let endA = end.a
  let endB = end.b
  const overlap = start - Math.min(endA, endB)
  if (overlap > 0) {
    endA += overlap
    endB += overlap
  }
  const snapped = old.isTextblock ? snapToWords(a, b, start, endA, endB) : { start, endA, endB }
  tr.replace(from + 1 + snapped.start, from + 1 + snapped.endA, next.slice(snapped.start, snapped.endB))
}

// Check the batch against `doc` and build the new document. Throws EditError, writing nothing.
export function planEdit(doc: PMNode, req: EditRequest): { doc: PMNode; result: EditResult } {
  const schema = blackboardSchema()
  const where = locate(doc)

  const unknown = req.ops.filter((o) => !where.has(o.blockId)).map((o) => o.blockId)
  if (unknown.length) throw new EditError('unknown_block', 'no block has these ids; read the document again', { block_ids: [...new Set(unknown)] })

  if (req.allowed) {
    const a = where.get(req.allowed.blockFrom)
    const b = where.get(req.allowed.blockTo)
    if (!a || !b) throw new EditError('out_of_scope', 'the blocks that bound the scope no longer exist', { allowed: req.allowed })
    const outside = req.ops.filter((o) => {
      const i = where.get(o.blockId)!.index
      return i < a.index || i > b.index
    })
    if (outside.length) throw new EditError('out_of_scope', 'these blocks are outside the scope', { block_ids: outside.map((o) => o.blockId) })
  }

  const rewritten = new Set<string>()
  for (const o of req.ops) {
    if (o.op !== 'replace' && o.op !== 'delete') continue
    if (rewritten.has(o.blockId)) throw new EditError('invalid', `block ${o.blockId} is replaced or deleted twice`, { block_id: o.blockId })
    rewritten.add(o.blockId)
  }

  // Compare-and-set: the digest covers pending suggestions too.
  const before = new Map<string, Block>()
  const touchedIds = [...new Set(req.ops.map((o) => o.blockId))]
  for (const id of touchedIds) before.set(id, blockInfo(where.get(id)!.node))
  const stale = req.ops
    .filter((o) => (o.op === 'replace' || o.op === 'delete') && before.get(o.blockId)!.digest !== o.digest)
    .map((o) => text(before.get(o.blockId)!))
  if (stale.length) {
    throw new EditError('stale', 'these blocks changed since they were read; read them again', { changed_blocks: dedupe(stale) })
  }

  // Someone else's pending suggestions in a block that would be rewritten must be decided first;
  // this mandate's own are reverted so the new text revises its proposal.
  const foreign: Array<{ block_id: string; suggestion_id: string; author: Author | null }> = []
  const own: Array<{ id: string; blockId: string }> = []
  for (const id of rewritten) {
    const b = where.get(id)!
    for (const s of suggestionsIn(doc, b.from, b.to)) {
      if (req.mandateId && s.author?.mandate === req.mandateId) own.push({ id: s.id, blockId: id })
      else foreign.push({ block_id: id, suggestion_id: s.id, author: s.author })
    }
  }
  if (foreign.length) {
    throw new EditError('pending_suggestions', 'these blocks hold pending suggestions from someone else; they need a decision first', {
      suggestions: foreign,
    })
  }

  // Parse everything first, so a bad fragment refuses the batch before anything is built.
  const parsed = req.ops.map((o, i) => (o.op === 'delete' ? [] : parseBlocks(o.markdown ?? '', i, req.author)))

  let state = EditorState.create({ schema, doc })
  for (const s of own) {
    const b = locate(state.doc).get(s.blockId)
    if (!b) continue
    revertSuggestion(s.id, b.from, b.to)(state, (t) => {
      state = state.apply(t)
    })
  }
  const current = locate(state.doc)
  const tr = state.tr
  const inserted: string[] = []
  req.ops.forEach((o, i) => {
    const b = current.get(o.blockId)!
    if (o.op === 'delete') {
      tr.delete(tr.mapping.map(b.from, 1), tr.mapping.map(b.to, -1))
    } else if (o.op === 'insert_after' || o.op === 'insert_before') {
      // Mapped to the right, so several inserts next to one block keep the order of the ops.
      tr.insert(tr.mapping.map(o.op === 'insert_after' ? b.to : b.from, 1), Fragment.fromArray(parsed[i]))
      inserted.push(...parsed[i].map((n) => n.attrs.id))
    } else if (parsed[i].length === 1 && sameMarkup(b.node, parsed[i][0])) {
      replaceInside(tr, tr.mapping.map(b.from, 1), b.node, parsed[i][0])
    } else {
      tr.replaceWith(tr.mapping.map(b.from, 1), tr.mapping.map(b.to, -1), Fragment.fromArray(parsed[i]))
      inserted.push(...parsed[i].map((n) => n.attrs.id))
    }
  })

  const beforeList = touchedIds.map((id) => text(before.get(id)!))
  if (!tr.docChanged && !own.length) return { doc, result: { changed: false, suggestionIds: [], before: beforeList, after: beforeList } }

  let out: Transaction = tr
  let suggestionIds: string[] = []
  if (req.mode === 'suggest' && tr.docChanged) {
    const suggested = suggestAttributed(tr, state, req.author)
    out = suggested.tr
    suggestionIds = suggested.ids
  }
  const next = out.doc
  next.check()

  const wanted = new Set([...touchedIds, ...inserted])
  const after: BlockText[] = []
  next.forEach((node) => {
    if (node.attrs.id && wanted.has(node.attrs.id)) after.push(text(blockInfo(node)))
  })
  return { doc: next, result: { changed: true, suggestionIds, before: beforeList, after } }
}

function dedupe(blocks: BlockText[]): BlockText[] {
  const seen = new Set<string | null>()
  return blocks.filter((b) => (seen.has(b.id) ? false : (seen.add(b.id), true)))
}
