// Markdown in and out: whole documents, single blocks, the accepted and proposed views, digests,
// and the agent view (Markdown with a <!-- block:<id> --> comment before every top-level block).
import { createHash } from 'node:crypto'
import { Extension } from '@tiptap/core'
import { MarkdownManager } from '@tiptap/markdown'
import type { Node as PMNode } from '@tiptap/pm/model'
import { Marked } from 'marked'
import { BLOCK_ID_TYPES, SUGGESTION_TYPES, blackboardExtensions, blackboardSchema, newBlockId } from '../schema/extensions.ts'

type Json = { type: string; attrs?: Record<string, any>; content?: Json[]; marks?: { type: string; attrs?: any }[]; text?: string }

export type View = 'accepted' | 'proposed'

export interface Block {
  id: string | null
  type: string
  markdown: string
  hasPendingSuggestions: boolean
  digest: string
}

export class MarkdownError extends Error {
  code: string
  details: Record<string, unknown>
  constructor(code: string, message: string, details: Record<string, unknown> = {}) {
    super(message)
    this.code = code
    this.details = details
  }
}

const BLOCK_COMMENT = /^<!-- block:([A-Za-z0-9_-]+) -->[ \t]*(?:\r?\n|$)/
// prosemirror-suggest-changes anchors some suggestions on zero-width spaces.
const ZWSP = /​/g

// Block-level tokenizer so `<!-- block:<id> -->` becomes a marker token instead of literal text.
const BlockIdComments = Extension.create({
  name: 'bbBlockIdComments',
  markdownTokenName: 'bbBlockId',
  markdownTokenizer: {
    name: 'bbBlockId',
    level: 'block',
    // Look only as far as the next blank line: a paragraph cannot run past it, and scanning the
    // whole remaining document at every block would make parsing quadratic.
    start: (src: string) => {
      const end = src.indexOf('\n\n')
      return (end < 0 ? src : src.slice(0, end)).indexOf('<!-- block:')
    },
    tokenize: (src: string) => {
      const m = BLOCK_COMMENT.exec(src)
      return m ? { type: 'bbBlockId', raw: m[0], id: m[1] } : undefined
    },
  },
  parseMarkdown: (token: any) => ({ type: 'bbBlockId', attrs: { id: token.id } }),
} as any)

export const sha256 = (text: string): string => createHash('sha256').update(text, 'utf8').digest('hex')

// Accepted view: pending insertions left out, pending deletions kept. Proposed view: the reverse.
export function viewJSON(json: Json, view: View): Json | null {
  const drop = view === 'accepted' ? 'insertion' : 'deletion'
  const walk = (node: Json): Json | null => {
    if ((node.marks || []).some((m) => m.type === drop)) return null
    const copy: Json = { ...node }
    if (copy.marks) {
      copy.marks = copy.marks.filter((m) => !SUGGESTION_TYPES.includes(m.type))
      if (!copy.marks.length) delete copy.marks
    }
    if (copy.type === 'text') {
      copy.text = (copy.text || '').replace(ZWSP, '')
      return copy.text ? copy : null
    }
    if (copy.content) copy.content = copy.content.map(walk).filter((n): n is Json => n !== null)
    return copy
  }
  return walk(json)
}

function hasSuggestionMarks(json: Json): boolean {
  if ((json.marks || []).some((m) => SUGGESTION_TYPES.includes(m.type))) return true
  return (json.content || []).some(hasSuggestionMarks)
}

function stripMarkers(nodes: Json[]): Json[] {
  return nodes
    .filter((n) => n.type !== 'bbBlockId')
    .map((n) => (n.content ? { ...n, content: stripMarkers(n.content) } : n))
}

// Images are block nodes in the schema; an image inside running text splits its paragraph.
const TEXTBLOCKS = new Set(['paragraph', 'heading'])
function liftInlineImages(nodes: Json[]): Json[] {
  const out: Json[] = []
  for (const node of nodes) {
    const n = node.content ? { ...node, content: liftInlineImages(node.content) } : node
    if (!TEXTBLOCKS.has(n.type) || !(n.content || []).some((c) => c.type === 'image')) {
      out.push(n)
      continue
    }
    let run: Json[] = []
    let first = true
    const flush = () => {
      // Markdown drops whitespace at the edges of a paragraph, so trim where the split happens.
      if (run.length && run[0].type === 'text') run[0] = { ...run[0], text: (run[0].text || '').replace(/^\s+/, '') }
      const last = run.length - 1
      if (run.length && run[last].type === 'text') run[last] = { ...run[last], text: (run[last].text || '').replace(/\s+$/, '') }
      run = run.filter((c) => c.type !== 'text' || c.text)
      const text = run.map((c) => c.text || '').join('')
      if (run.length && (text.trim() || run.some((c) => c.type !== 'text'))) {
        const attrs = { ...(n.attrs || {}) }
        if (!first) delete attrs.id
        out.push({ ...n, attrs, content: run })
        first = false
      }
      run = []
    }
    for (const c of n.content || []) {
      if (c.type === 'image') {
        flush()
        out.push(c)
      } else {
        run.push(c)
      }
    }
    flush()
  }
  return out
}

// One manager per process with a private Marked instance: the default instance is global, and
// every MarkdownManager registers its tokenizers on it again.
const manager = new MarkdownManager({ extensions: [...blackboardExtensions(), BlockIdComments], marked: new Marked() } as any)

export function parseMarkdown(markdown: string): Json {
  const json = manager.parse(markdown) as Json
  return { type: 'doc', content: liftInlineImages(stripMarkers(json.content || [])) }
}

export function serializeMarkdown(json: Json): string {
  return manager.serialize(json as any)
}

export function serializeBlock(node: Json): string {
  // An empty paragraph alone serializes to nothing and would vanish from the agent view.
  if (node.type === 'paragraph' && !(node.content && node.content.length)) return '&nbsp;'
  return manager.serialize({ type: 'doc', content: [node] } as any).trim()
}

// Give every block type in BLOCK_ID_TYPES a fresh id, at any depth.
export function assignFreshIds(json: Json): Json {
  const walk = (node: Json): Json => {
    const copy = { ...node }
    if (BLOCK_ID_TYPES.includes(copy.type)) copy.attrs = { ...(copy.attrs || {}), id: newBlockId() }
    if (copy.content) copy.content = copy.content.map(walk)
    return copy
  }
  return walk(json)
}

// Parse Markdown into a valid document with fresh block ids; raw HTML stays literal text.
export function importDoc(markdown: string): PMNode {
  const json = assignFreshIds(parseMarkdown(markdown))
  if (!json.content || !json.content.length) json.content = [{ type: 'paragraph', attrs: { id: newBlockId() } }]
  const node = blackboardSchema().nodeFromJSON(json)
  node.check()
  return node
}

export function hasRawHtml(markdown: string): boolean {
  return /<(?!br\s*\/?>|!-- block:)[A-Za-z!/][^>]*>/i.test(markdown)
}

// Top-level blocks with the accepted Markdown and a digest. The digest covers the proposed view
// too when a block has pending suggestions: adding a suggestion does not change the accepted view,
// so a digest over it alone would let a second edit land on top of the first one's suggestions.
export function blocksOf(doc: PMNode): Block[] {
  const out: Block[] = []
  doc.forEach((node) => {
    const json = node.toJSON() as Json
    const pending = hasSuggestionMarks(json)
    const acceptedNode = viewJSON(json, 'accepted')
    const accepted = acceptedNode ? serializeBlock(acceptedNode) : ''
    let digest = sha256(accepted)
    if (pending) {
      const proposedNode = viewJSON(json, 'proposed')
      digest = sha256(`${accepted}\n\n${proposedNode ? serializeBlock(proposedNode) : ''}`)
    }
    out.push({ id: node.attrs.id ?? null, type: node.type.name, markdown: accepted, hasPendingSuggestions: pending, digest })
  })
  return out
}

// The agent view: `<!-- block:<id> -->` and the block's Markdown, for every top-level block or a
// contiguous range `fromId..toId`.
export function agentView(doc: PMNode, { view = 'accepted', range = null }: { view?: View; range?: string | null } = {}) {
  let blocks = blocksOf(doc)
  if (range) {
    const [fromId, toId] = range.split('..')
    const from = blocks.findIndex((b) => b.id === fromId)
    const to = blocks.findIndex((b) => b.id === (toId || fromId))
    if (from < 0 || to < 0 || to < from) throw new MarkdownError('unknown_block', 'the range does not name two blocks in order', { range })
    blocks = blocks.slice(from, to + 1)
  }
  const texts = blocks.map((b) => {
    if (view === 'accepted' || !b.hasPendingSuggestions) return b.markdown
    let proposed = ''
    doc.forEach((node) => {
      if (node.attrs.id === b.id) {
        const p = viewJSON(node.toJSON() as Json, 'proposed')
        proposed = p ? serializeBlock(p) : ''
      }
    })
    return proposed
  })
  return {
    markdown: blocks.map((b, i) => `<!-- block:${b.id} -->\n${texts[i] || '&nbsp;'}`).join('\n\n') + '\n',
    blocks: blocks.map(({ id, type, digest, hasPendingSuggestions }) => ({ id, type, digest, hasPendingSuggestions })),
  }
}
