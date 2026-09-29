// Suggestions on top of @handlewithcare/prosemirror-suggest-changes: turning a plain transaction
// into suggestions by an author, the attribution pass, and listing what a document holds.
import { transformToSuggestionTransaction } from '@handlewithcare/prosemirror-suggest-changes'
import type { Mark, Node as PMNode } from '@tiptap/pm/model'
import type { EditorState, Transaction } from '@tiptap/pm/state'
import { ReplaceStep } from '@tiptap/pm/transform'
import { SUGGESTION_TYPES } from '../schema/extensions.ts'

export interface Author {
  id: string
  kind: 'person' | 'agent'
  mandate?: string | null
}

// A suggestion: its marks' types, who made it, and the text it inserts and deletes. A replacement is
// one suggestion that does both.
export interface SuggestionSummary {
  id: string
  types: string[]
  author: Author | null
  inserted: string
  deleted: string
}

// prosemirror-suggest-changes anchors some suggestions on zero-width spaces.
const ZWSP = new RegExp(String.fromCharCode(0x200b), 'g')
const isSuggestion = (mark: Mark) => SUGGESTION_TYPES.includes(mark.type.name)

let seq = 0
// Ids start with a letter and are unique across clients (the library's default is the highest id
// in the document plus one, which two clients would both pick).
export function newSuggestionId(): string {
  seq += 1
  return 's' + Date.now().toString(36) + seq.toString(36) + Math.random().toString(36).slice(2, 7)
}

// Put `author` on every suggestion mark whose id is in `ids`.
function stampSuggestionAuthor(tr: Transaction, ids: Set<string>, author: Author): void {
  const edits: Array<{ node: PMNode; pos: number; mark: Mark }> = []
  tr.doc.descendants((node, pos) => {
    for (const mark of node.marks) if (isSuggestion(mark) && ids.has(mark.attrs.id)) edits.push({ node, pos, mark })
  })
  for (const { node, pos, mark } of edits) {
    const stamped = mark.type.create({ ...mark.attrs, author })
    if (node.isInline) {
      tr.removeMark(pos, pos + node.nodeSize, mark)
      tr.addMark(pos, pos + node.nodeSize, stamped)
    } else {
      tr.removeNodeMark(pos, mark)
      tr.addNodeMark(pos, stamped)
    }
  }
}

// [from, to) minus a list of ranges.
function subtract([from, to]: [number, number], cuts: Array<[number, number]>): Array<[number, number]> {
  let parts: Array<[number, number]> = [[from, to]]
  for (const [a, b] of cuts) {
    const next: Array<[number, number]> = []
    for (const [x, y] of parts) {
      if (b <= x || a >= y) next.push([x, y])
      else {
        if (a > x) next.push([x, a])
        if (b < y) next.push([b, y])
      }
    }
    parts = next
  }
  return parts.filter(([x, y]) => y > x)
}

// Turn `tr` (built on `state`) into suggestions by `author`. The library joins a new suggestion that
// touches an existing one into the existing id, whatever the author (spike 2), so an attribution
// pass follows: old suggestion marks go back on old content, and new content that ended up under an
// old id gets a fresh id and this author. Returns the transaction and the ids it created.
export function suggestAttributed(tr: Transaction, state: EditorState, author: Author): { tr: Transaction; ids: string[] } {
  const oldInline: Array<{ from: number; to: number; mark: Mark }> = []
  const oldNodes: Array<{ pos: number; mark: Mark }> = []
  state.doc.descendants((node, pos) => {
    for (const mark of node.marks) {
      if (!isSuggestion(mark)) continue
      if (node.isInline) oldInline.push({ from: pos, to: pos + node.nodeSize, mark })
      else oldNodes.push({ pos, mark })
    }
  })
  const oldIds = new Set([...oldInline, ...oldNodes].map((x) => x.mark.attrs.id as string))

  const created = new Set<string>()
  const out = transformToSuggestionTransaction(tr, state, () => {
    const id = newSuggestionId()
    created.add(id)
    return id
  }) as Transaction
  stampSuggestionAuthor(out, created, author)
  const n = out.steps.length

  // Ranges of the final document that the transformed transaction inserted.
  const inserted: Array<[number, number]> = []
  for (let i = 0; i < n; i++) {
    const step = out.steps[i]
    if (!(step instanceof ReplaceStep) || (step as any).slice.size === 0) continue
    let a = (step as any).from as number
    let b = a + (step as any).slice.size
    for (let j = i + 1; j < n; j++) {
      const m = out.steps[j].getMap()
      a = m.map(a, 1)
      b = m.map(b, -1)
    }
    if (b > a) inserted.push([a, b])
  }
  const mapping = out.mapping.slice(0, n)

  // 1. Old inline suggestions keep their own mark on old content.
  const kept: Array<{ from: number; to: number; mark: Mark }> = []
  for (const { from, to, mark } of oldInline) {
    const a = mapping.map(from, 1)
    const b = mapping.map(to, -1)
    if (b <= a) continue
    for (const [x, y] of subtract([a, b], inserted)) {
      out.removeMark(x, y, mark.type)
      out.addMark(x, y, mark)
      kept.push({ from: x, to: y, mark })
    }
  }
  // 2. Old node suggestions likewise.
  const keptNodes = new Map<number, string>()
  for (const { pos, mark } of oldNodes) {
    const r = mapping.mapResult(pos, 1)
    if (r.deleted) continue
    const node = out.doc.nodeAt(r.pos)
    if (!node) continue
    const current = node.marks.find((m) => m.type === mark.type)
    if (current) out.removeNodeMark(r.pos, current)
    out.addNodeMark(r.pos, mark)
    keptNodes.set(r.pos, mark.attrs.id)
  }
  // 3. New content under an old id gets a fresh id (one per old id) and this author.
  const fresh = new Map<string, string>()
  const freshId = (oldId: string) => {
    if (!fresh.has(oldId)) fresh.set(oldId, newSuggestionId())
    return fresh.get(oldId)!
  }
  const relabel: Array<{ inline: boolean; from: number; to: number; mark: Mark }> = []
  out.doc.descendants((node, pos) => {
    for (const mark of node.marks) {
      if (!isSuggestion(mark) || !oldIds.has(mark.attrs.id)) continue
      if (node.isInline) {
        const cover = kept.filter((k) => k.mark.type === mark.type && k.mark.attrs.id === mark.attrs.id).map((k): [number, number] => [k.from, k.to])
        for (const [x, y] of subtract([pos, pos + node.nodeSize], cover)) relabel.push({ inline: true, from: x, to: y, mark })
      } else if (keptNodes.get(pos) !== mark.attrs.id) {
        relabel.push({ inline: false, from: pos, to: pos, mark })
      }
    }
  })
  for (const r of relabel) {
    const next = r.mark.type.create({ ...r.mark.attrs, id: freshId(r.mark.attrs.id), author })
    if (r.inline) {
      out.removeMark(r.from, r.to, r.mark.type)
      out.addMark(r.from, r.to, next)
    } else {
      out.removeNodeMark(r.from, r.mark)
      out.addNodeMark(r.from, next)
    }
  }

  const ids = new Set<string>()
  out.doc.descendants((node) => {
    for (const mark of node.marks) if (isSuggestion(mark) && !oldIds.has(mark.attrs.id)) ids.add(mark.attrs.id)
  })
  return { tr: out, ids: [...ids] }
}

// Pending suggestions inside [from, to) of `doc`, or in the whole document.
export function suggestionsIn(doc: PMNode, from = 0, to = doc.content.size): SuggestionSummary[] {
  const found = new Map<string, SuggestionSummary & { typeSet: Set<string> }>()
  doc.nodesBetween(from, to, (node) => {
    for (const mark of node.marks) {
      if (!isSuggestion(mark)) continue
      const entry = found.get(mark.attrs.id) ?? { id: mark.attrs.id, types: [], typeSet: new Set<string>(), author: null, inserted: '', deleted: '' }
      entry.typeSet.add(mark.type.name)
      entry.author = entry.author ?? mark.attrs.author ?? null
      // A whole-block suggestion marks the block, not its text.
      const text = (node.isText ? (node.text ?? '') : node.textContent).replace(ZWSP, '')
      if (mark.type.name === 'insertion') entry.inserted += text
      else if (mark.type.name === 'deletion') entry.deleted += text
      found.set(mark.attrs.id, entry)
    }
  })
  return [...found.values()].map(({ typeSet, ...s }) => ({ ...s, types: [...typeSet].sort() }))
}
