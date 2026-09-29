// Comment anchors: a passage held as two Yjs relative positions and the text it quoted. Resolving an
// anchor against the live document says whether the passage is still there (ok), changed underneath
// (drifted), or cannot be found (orphaned). Text is read in the accepted view: a pending suggestion
// on a passage does not change it until someone accepts it. When the positions no longer hold the
// passage, the quote is searched in the original block, then in a block with the same digest, then
// in the whole document; exactly one match moves the anchor there, anything else leaves it
// orphaned. A thread is never attached to text it did not quote.
import type { Node as PMNode } from '@tiptap/pm/model'
import * as Y from 'yjs'
import { absolutePositionToRelativePosition, initProseMirrorDoc, relativePositionToAbsolutePosition } from '../../vendor/y-tiptap-nodemarks.js'
import { blackboardSchema } from '../schema/extensions.ts'
import { blockInfo } from './markdown.ts'
import { FIELD } from './pool.ts'

// The block separator of quotes; the browser takes a selection's quote with the same one.
export const SEPARATOR = '\n'
export const MAX_ANCHORS = 200

export interface Anchor {
  block_id: string
  block_to?: string | null
  digest?: string | null
  start: string
  end: string
  quote: string
}

export interface Resolved {
  status: 'ok' | 'drifted' | 'orphaned'
  from?: number
  to?: number
  block_id?: string | null
  block_to?: string | null
  // New relative positions and first-block offset, when the anchor moved.
  start?: string
  end?: string
  offset?: number
  digest?: string
  quote_now?: string
}

type Mapping = Map<any, any>

const normalize = (text: string): string => text.split(/\s+/).filter(Boolean).join(' ')

function decode(position: string): Y.RelativePosition | null {
  try {
    return Y.decodeRelativePosition(Uint8Array.from(Buffer.from(position, 'base64')))
  } catch {
    return null
  }
}

export function encode(position: Y.RelativePosition): string {
  return Buffer.from(Y.encodeRelativePosition(position)).toString('base64')
}

const suggestedInsertion = (node: PMNode): boolean => node.marks.some((m) => m.type.name === 'insertion')

// The accepted text between two positions with the document position of every character, following
// ProseMirror's textBetween (a separator before each text block but the first); text a pending
// suggestion inserts is left out.
export function textWithPositions(doc: PMNode, from: number, to: number): { text: string; positions: number[] } {
  let text = ''
  const positions: number[] = []
  let first = true
  doc.nodesBetween(from, to, (node, pos) => {
    if (node.isBlock && (node.isTextblock || (node.isLeaf && node.type.spec.leafText))) {
      if (first) first = false
      else {
        text += SEPARATOR
        positions.push(pos)
      }
    }
    if (node.isText && !suggestedInsertion(node)) {
      const start = Math.max(from, pos)
      const piece = node.text!.slice(start - pos, to - pos)
      for (let i = 0; i < piece.length; i++) positions.push(start + i)
      text += piece
    } else if (node.isLeaf && node.type.spec.leafText) {
      const piece = node.type.spec.leafText(node)
      for (let i = 0; i < piece.length; i++) positions.push(pos)
      text += piece
    }
  })
  return { text, positions }
}

interface Block {
  id: string | null
  pos: number
  node: PMNode
}

function topBlocks(doc: PMNode): Block[] {
  const blocks: Block[] = []
  doc.forEach((node, pos) => blocks.push({ id: node.attrs.id ?? null, pos, node }))
  return blocks
}

function blockAt(blocks: Block[], pos: number): Block | undefined {
  return blocks.find((b) => pos >= b.pos && pos < b.pos + b.node.nodeSize) ?? blocks[blocks.length - 1]
}

// Where `quote` occurs within [from, to): each match as document positions.
function matches(doc: PMNode, from: number, to: number, quote: string): Array<{ from: number; to: number }> {
  const { text, positions } = textWithPositions(doc, from, to)
  const out: Array<{ from: number; to: number }> = []
  let at = text.indexOf(quote)
  while (at >= 0) {
    out.push({ from: positions[at], to: positions[at + quote.length - 1] + 1 })
    at = text.indexOf(quote, at + 1)
  }
  return out
}

function moved(doc: PMNode, fragment: Y.XmlFragment, mapping: Mapping, blocks: Block[], found: { from: number; to: number }): Resolved {
  const first = blockAt(blocks, found.from)!
  const last = blockAt(blocks, found.to - 1)!
  return {
    status: 'ok',
    from: found.from,
    to: found.to,
    block_id: first.id,
    block_to: last.id,
    start: encode(absolutePositionToRelativePosition(found.from, fragment, mapping)),
    end: encode(absolutePositionToRelativePosition(found.to, fragment, mapping)),
    offset: textWithPositions(doc, first.pos, found.from).text.length,
    digest: blockInfo(first.node).digest,
    quote_now: textWithPositions(doc, found.from, found.to).text,
  }
}

function search(doc: PMNode, fragment: Y.XmlFragment, mapping: Mapping, blocks: Block[], anchor: Anchor): Resolved {
  const quote = anchor.quote
  const inBlocks = (candidates: Block[]) => candidates.flatMap((b) => matches(doc, b.pos, b.pos + b.node.nodeSize, quote))
  const byId = blocks.filter((b) => b.id !== null && b.id === anchor.block_id)
  const byDigest = anchor.digest ? blocks.filter((b) => blockInfo(b.node).digest === anchor.digest) : []
  for (const found of [inBlocks(byId), inBlocks(byDigest), matches(doc, 0, doc.content.size, quote)]) {
    if (found.length === 1) return moved(doc, fragment, mapping, blocks, found[0])
    if (found.length > 1) return { status: 'orphaned' }
  }
  return { status: 'orphaned' }
}

export function resolveAnchors(ydoc: Y.Doc, anchors: Anchor[]): Resolved[] {
  const fragment = ydoc.getXmlFragment(FIELD)
  const { doc, mapping } = initProseMirrorDoc(fragment, blackboardSchema()) as { doc: PMNode; mapping: Mapping }
  const blocks = topBlocks(doc)
  return anchors.map((anchor) => {
    const start = decode(anchor.start)
    const end = decode(anchor.end)
    const from = start ? relativePositionToAbsolutePosition(ydoc, fragment, start, mapping) : null
    const to = end ? relativePositionToAbsolutePosition(ydoc, fragment, end, mapping) : null
    if (from !== null && to !== null && from < to) {
      const now = textWithPositions(doc, from, to).text
      const common = { from, to, block_id: blockAt(blocks, from)?.id ?? null, block_to: blockAt(blocks, to - 1)?.id ?? null, quote_now: now }
      if (normalize(now) === normalize(anchor.quote)) return { status: 'ok', ...common }
      // The passage is where it was but its text changed: a thread about it still belongs there.
      if (normalize(now)) return { status: 'drifted', ...common }
    }
    return search(doc, fragment, mapping, blocks, anchor)
  })
}

export function readAnchors(value: unknown): Anchor[] {
  if (!Array.isArray(value) || value.length > MAX_ANCHORS) throw new TypeError(`anchors is a list of at most ${MAX_ANCHORS}`)
  return value.map((a: any, i) => {
    if (!a || typeof a.start !== 'string' || typeof a.end !== 'string' || typeof a.quote !== 'string' || typeof a.block_id !== 'string') {
      throw new TypeError(`anchor ${i} needs block_id, start, end and quote`)
    }
    return { block_id: a.block_id, block_to: a.block_to ?? null, digest: a.digest ?? null, start: a.start, end: a.end, quote: a.quote }
  })
}
