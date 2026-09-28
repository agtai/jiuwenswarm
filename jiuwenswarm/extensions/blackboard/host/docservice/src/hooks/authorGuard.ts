// Author guard: a person's update may not add text credited to anyone else. People write as
// themselves; agent text is written by the service itself (milestone 4).
//
// The check compares credits before and after the update, on a copy of the document, instead of
// reading the marks inside the update: the editor's Yjs binding legitimately writes other people's
// marks when it recreates their text (splitting or joining a paragraph, moving a block), and Yjs
// writes a format item that restores the previous author after every insertion.
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
  walk(doc.getXmlFragment(YJS_FIELD), [])
  return credits
}

export interface AuthorProblem {
  mark: string
  problem: string
}

// Problems with applying `update` from the person `userId` to `doc`; empty when it is fine.
export function authorProblems(doc: Y.Doc, update: Uint8Array, userId: string): AuthorProblem[] {
  const { structs, ds } = Y.decodeUpdate(update)
  if (structs.length === 0 && ds.clients.size === 0) return []
  const before = creditsOf(doc)
  const copy = new Y.Doc()
  Y.applyUpdate(copy, Y.encodeStateAsUpdate(doc))
  Y.applyUpdate(copy, update)
  const after = creditsOf(copy)
  copy.destroy()
  const me = `person:${userId}`
  const problems: AuthorProblem[] = []
  for (const [key, amount] of after) {
    const [mark, who] = key.split('\u0000')
    const was = before.get(key) ?? 0
    if (who !== me && amount > was) problems.push({ mark, problem: `adds ${amount - was} to ${who}` })
  }
  return problems
}

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
  const problems = authorProblems(document, inner, context.userId)
  if (problems.length) throw new AuthorMismatch(problems)
}
