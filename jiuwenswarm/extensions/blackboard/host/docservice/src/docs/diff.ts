// The difference between two versions, block by block: there are no steps between two arbitrary
// snapshots, so top-level blocks are matched by id. Blocks are compared in the proposed view, so an
// agent's pending suggestions show as the change they propose; `pending` and `wasPending` say
// whether a block holds suggestions in each version (a suggestion accepted without other changes
// leaves the text the same and only clears `pending`).
import { diffWords } from 'diff'
import type { Node as PMNode } from '@tiptap/pm/model'
import { hasSuggestionMarks, serializeBlock, viewJSON } from './markdown.ts'

export type BlockStatus = 'unchanged' | 'changed' | 'added' | 'removed' | 'moved'

export interface InlinePart {
  op: 'eq' | 'ins' | 'del'
  text: string
}

export interface DiffBlock {
  id: string | null
  type: string
  status: BlockStatus
  markdown: string
  inline?: InlinePart[]
  pending: boolean
  wasPending: boolean
}

export interface DocDiff {
  blocks: DiffBlock[]
  summary: Record<BlockStatus, number>
}

interface Side {
  key: string
  id: string | null
  type: string
  markdown: string
  pending: boolean
}

function sides(doc: PMNode | null, prefix: string): Side[] {
  const out: Side[] = []
  doc?.forEach((node, _offset, index) => {
    const json = node.toJSON()
    const proposed = viewJSON(json, 'proposed')
    const markdown = proposed ? serializeBlock(proposed) : ''
    out.push({
      key: node.attrs.id ?? `${prefix}${index}`,
      id: node.attrs.id ?? null,
      type: node.type.name,
      markdown: markdown === '&nbsp;' ? '' : markdown,
      pending: hasSuggestionMarks(json),
    })
  })
  return out
}

// The blocks that kept their order: with unique ids the longest common subsequence is the longest
// increasing run of old positions, read in the new order.
function keptInOrder(from: Side[], to: Side[]): Set<string> {
  const position = new Map(from.map((s, i) => [s.key, i]))
  const seq = to.filter((s) => position.has(s.key)).map((s) => ({ key: s.key, at: position.get(s.key)! }))
  const tails: number[] = []
  const previous: number[] = new Array(seq.length).fill(-1)
  for (let i = 0; i < seq.length; i++) {
    let lo = 0
    let hi = tails.length
    while (lo < hi) {
      const mid = (lo + hi) >> 1
      if (seq[tails[mid]].at < seq[i].at) lo = mid + 1
      else hi = mid
    }
    if (lo > 0) previous[i] = tails[lo - 1]
    tails[lo] = i
  }
  const kept = new Set<string>()
  for (let i = tails.length ? tails[tails.length - 1] : -1; i >= 0; i = previous[i]) kept.add(seq[i].key)
  return kept
}

function inline(before: string, after: string): InlinePart[] {
  return diffWords(before, after).map((part) => ({ op: part.added ? 'ins' : part.removed ? 'del' : 'eq', text: part.value }))
}

function compared(before: Side, after: Side, moved: boolean): DiffBlock {
  const same = before.markdown === after.markdown
  return {
    id: after.id,
    type: after.type,
    status: moved ? 'moved' : same ? 'unchanged' : 'changed',
    markdown: after.markdown,
    ...(same ? {} : { inline: inline(before.markdown, after.markdown) }),
    pending: after.pending,
    wasPending: before.pending,
  }
}

// `from` null compares against an empty document: every block is added.
export function diffDocs(from: PMNode | null, to: PMNode): DocDiff {
  const a = sides(from, 'a:')
  const b = sides(to, 'b:')
  const inA = new Map(a.map((s, i) => [s.key, i]))
  const inB = new Set(b.map((s) => s.key))
  const kept = keptInOrder(a, b)
  const blocks: DiffBlock[] = []
  let i = 0
  let j = 0
  while (i < a.length || j < b.length) {
    if (i < a.length && !inB.has(a[i].key)) {
      const s = a[i++]
      blocks.push({ id: s.id, type: s.type, status: 'removed', markdown: s.markdown, pending: false, wasPending: s.pending })
      continue
    }
    if (i < a.length && !kept.has(a[i].key)) {
      i++ // moved: shown where it is now
      continue
    }
    if (j < b.length && !inA.has(b[j].key)) {
      const s = b[j++]
      blocks.push({ id: s.id, type: s.type, status: 'added', markdown: s.markdown, pending: s.pending, wasPending: false })
      continue
    }
    if (j < b.length && !kept.has(b[j].key)) {
      blocks.push(compared(a[inA.get(b[j].key)!], b[j], true))
      j++
      continue
    }
    // Both at the next block that kept its place.
    blocks.push(compared(a[i], b[j], false))
    i++
    j++
  }
  const summary: Record<BlockStatus, number> = { unchanged: 0, changed: 0, added: 0, removed: 0, moved: 0 }
  for (const block of blocks) summary[block.status] += 1
  return { blocks, summary }
}
