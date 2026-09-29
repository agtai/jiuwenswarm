// Author guard: a person's update may not add text credited to anyone else. People write as
// themselves; agent text is written by the service itself (milestone 4).
//
// The check compares credits before and after the update instead of reading the marks inside the
// update: the editor's Yjs binding legitimately writes other people's marks when it recreates their
// text (splitting or joining a paragraph, moving a block), and Yjs writes a format item that restores
// the previous author after every insertion. A ledger per open document keeps a shadow copy and the
// credits of each top-level block, so an update is counted only in the blocks it touches.
import * as Y from 'yjs'
import * as decoding from 'lib0/decoding'
import { SUGGESTION_TYPES, YJS_FIELD } from '../schema/extensions.ts'

// Message: varString(document name), varUint(type). Types 0 (Sync) and 4 (SyncReply) both carry
// sync data: varUint(step) and, for step 2 and updates, varUint8Array(update). The official provider
// sends type 0 only, but the server applies both, so both are checked.
export function extractUpdate(message: Uint8Array): Uint8Array | null {
  const dec = decoding.createDecoder(message)
  decoding.readVarString(dec)
  const type = decoding.readVarUint(dec)
  if (type !== 0 && type !== 4) return null
  const step = decoding.readVarUint(dec)
  if (step !== 1 && step !== 2) return null
  return decoding.readVarUint8Array(dec)
}

// "<mark>\u0000<kind>:<id>" -> characters credited (a leaf block without text counts as one).
export type Credits = Map<string, number>

function credit(credits: Credits, mark: string, who: any, amount: number): void {
  if (!who || typeof who !== 'object' || typeof who.id !== 'string') return
  const key = `${mark}\u0000${who.kind ?? '?'}:${who.id}`
  credits.set(key, (credits.get(key) ?? 0) + amount)
}

export function creditsOf(doc: Y.Doc): Credits {
  const credits: Credits = new Map()
  addCredits(credits, doc.getXmlFragment(YJS_FIELD))
  return credits
}

function addCredits(credits: Credits, root: Y.XmlFragment | Y.XmlElement | Y.XmlText): void {
  // Node marks (the patched y-tiptap) are element attributes named _mark_<name>; they credit the
  // text inside the element.
  const walk = (type: Y.XmlFragment | Y.XmlElement | Y.XmlText, inherited: Array<[string, any]>) => {
    if (type instanceof Y.XmlText) {
      for (const op of type.toDelta() as Array<{ insert: unknown; attributes?: Record<string, any> }>) {
        if (typeof op.insert !== 'string') continue
        const amount = op.insert.length
        const attrs = op.attributes ?? {}
        credit(credits, 'author', attrs.author, amount)
        for (const key of SUGGESTION_TYPES) credit(credits, key, attrs[key]?.author, amount)
        for (const [mark, who] of inherited) credit(credits, mark, who, amount)
      }
      return
    }
    let marks = inherited
    if (type instanceof Y.XmlElement) {
      const own = Object.entries(type.getAttributes())
        .filter(([key, value]: [string, any]) => key.startsWith('_mark_') && value?.author)
        .map(([key, value]: [string, any]): [string, any] => [key, value.author])
      if (own.length) {
        marks = [...inherited, ...own]
        if (type.length === 0) for (const [mark, who] of own) credit(credits, mark, who, 1)
      }
    }
    for (const child of type.toArray()) {
      if (child instanceof Y.XmlElement || child instanceof Y.XmlText) walk(child, marks)
    }
  }
  walk(root, [])
}

export interface AuthorProblem {
  mark: string
  problem: string
}

function compare(before: Credits, after: Credits, userId: string): AuthorProblem[] {
  const me = `person:${userId}`
  const problems: AuthorProblem[] = []
  for (const [key, amount] of after) {
    const [mark, who] = key.split('\u0000')
    const was = before.get(key) ?? 0
    if (who !== me && amount > was) problems.push({ mark, problem: `adds ${amount - was} to ${who}` })
  }
  return problems
}

function sum(parts: Iterable<Credits>): Credits {
  const total: Credits = new Map()
  for (const part of parts) for (const [key, amount] of part) total.set(key, (total.get(key) ?? 0) + amount)
  return total
}

// Problems with applying `update` from the person `userId` to `doc`; empty when it is fine. The
// whole-document check, kept as the reference the ledger is tested against.
export function authorProblems(doc: Y.Doc, update: Uint8Array, userId: string): AuthorProblem[] {
  const { structs, ds } = Y.decodeUpdate(update)
  if (structs.length === 0 && ds.clients.size === 0) return []
  const before = creditsOf(doc)
  const copy = new Y.Doc()
  Y.applyUpdate(copy, Y.encodeStateAsUpdate(doc))
  Y.applyUpdate(copy, update)
  const after = creditsOf(copy)
  copy.destroy()
  return compare(before, after, userId)
}

type Block = Y.XmlElement | Y.XmlText

// A shadow copy of an open document and the credits of each of its top-level blocks. It follows
// every update the document takes; a person's update is applied to the shadow first, and only the
// blocks it touched, added or removed are counted again.
export class CreditLedger {
  private shadow!: Y.Doc
  private blocks = new Map<Block, Credits>()
  private touched = new Set<Y.AbstractType<any>>()
  private readonly live: Y.Doc

  constructor(live: Y.Doc) {
    this.live = live
    this.reset()
    live.on('update', (update: Uint8Array) => {
      this.blocks = this.apply(update)
    })
  }

  // Problems with `update` from the person `userId`; when there are none the shadow keeps it.
  check(update: Uint8Array, userId: string): AuthorProblem[] {
    const previous = this.blocks
    const next = this.apply(update)
    const before: Credits[] = []
    const after: Credits[] = []
    for (const [block, credits] of next) {
      const old = previous.get(block)
      if (old === credits) continue
      after.push(credits)
      if (old) before.push(old)
    }
    for (const [block, credits] of previous) if (!next.has(block)) before.push(credits)
    const problems = compare(sum(before), sum(after), userId)
    // The document will not take a refused update, so the shadow starts again from it.
    if (problems.length) this.reset()
    else this.blocks = next
    return problems
  }

  private reset(): void {
    this.shadow?.destroy()
    this.shadow = new Y.Doc()
    this.shadow.on('afterTransaction', (tr: Y.Transaction) => {
      for (const type of tr.changed.keys()) this.touched.add(type)
      for (const type of tr.changedParentTypes.keys()) this.touched.add(type)
    })
    Y.applyUpdate(this.shadow, Y.encodeStateAsUpdate(this.live))
    this.touched.clear()
    this.blocks = new Map(this.children().map((block) => [block, blockCredits(block)]))
  }

  private children(): Block[] {
    return this.shadow
      .getXmlFragment(YJS_FIELD)
      .toArray()
      .filter((child): child is Block => child instanceof Y.XmlElement || child instanceof Y.XmlText)
  }

  // Each top-level block's credits after `update`, counted again where the update changed it.
  private apply(update: Uint8Array): Map<Block, Credits> {
    this.touched.clear()
    Y.applyUpdate(this.shadow, update)
    const fragment = this.shadow.getXmlFragment(YJS_FIELD)
    const changed = new Set<Y.AbstractType<any>>()
    for (const type of this.touched) {
      let top: Y.AbstractType<any> | null = type
      while (top && top.parent && top.parent !== fragment) top = top.parent
      if (top && top.parent === fragment) changed.add(top)
    }
    this.touched.clear()
    const next = new Map<Block, Credits>()
    for (const block of this.children()) {
      const known = this.blocks.get(block)
      next.set(block, known && !changed.has(block) ? known : blockCredits(block))
    }
    return next
  }
}

function blockCredits(block: Block): Credits {
  const credits: Credits = new Map()
  addCredits(credits, block)
  return credits
}

const ledgers = new WeakMap<Y.Doc, CreditLedger>()

export class AuthorMismatch extends Error {
  reason = 'author_mismatch'
  problems: AuthorProblem[]
  constructor(problems: AuthorProblem[]) {
    super('author_mismatch')
    this.problems = problems
  }
}

// Hocuspocus beforeHandleMessage: throwing closes that document connection and drops the message.
export function authorGuard({ update, context, document }: { update: Uint8Array; context: any; document: Y.Doc }): void {
  if (!context || context.kind !== 'person') return
  const inner = extractUpdate(update)
  if (!inner) return
  const { structs, ds } = Y.decodeUpdate(inner)
  if (structs.length === 0 && ds.clients.size === 0) return
  let ledger = ledgers.get(document)
  if (!ledger) {
    ledger = new CreditLedger(document)
    ledgers.set(document, ledger)
  }
  const problems = ledger.check(inner, context.userId)
  if (problems.length) throw new AuthorMismatch(problems)
}
