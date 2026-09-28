// Server-side reads and writes of documents, without a Tiptap Editor or a DOM: the Y.XmlFragment
// becomes a ProseMirror node, a change is made on an EditorState, and updateYFragment writes the
// new document back, touching only the blocks and text that changed. Everything runs inside one
// transaction on a Hocuspocus direct connection.
import type { Hocuspocus } from '@hocuspocus/server'
import type { Node as PMNode } from '@tiptap/pm/model'
import * as Y from 'yjs'
import { updateYFragment, yXmlFragmentToProseMirrorRootNode } from '../../vendor/y-tiptap-nodemarks.js'
import { YJS_FIELD, blackboardSchema } from '../schema/extensions.ts'

export const FIELD = YJS_FIELD

const SERVICE_CONTEXT = { userId: 'service', kind: 'service' }

export function readDoc(ydoc: Y.Doc): PMNode {
  return yXmlFragmentToProseMirrorRootNode(ydoc.getXmlFragment(FIELD), blackboardSchema())
}

export function writeDoc(ydoc: Y.Doc, doc: PMNode): void {
  const fragment = ydoc.getXmlFragment(FIELD)
  ydoc.transact(() => updateYFragment(ydoc, fragment, doc, { mapping: new Map(), isOMark: new Map() } as any))
}

export class DocPool {
  private hocuspocus: Hocuspocus
  // One promise chain per document, so two API calls on a document never interleave.
  private chains = new Map<string, Promise<unknown>>()

  constructor(hocuspocus: Hocuspocus) {
    this.hocuspocus = hocuspocus
  }

  // Run `fn` on the document's Y.Doc inside a transaction. `immediate` saves the document before
  // returning: writes that must survive a crash (imports, agent edits, restores) use it, because a
  // crash otherwise loses up to maxDebounce of changes when no browser is left to resend them.
  run<T>(docId: string, fn: (ydoc: Y.Doc) => T, { immediate = false } = {}): Promise<T> {
    const previous = this.chains.get(docId) ?? Promise.resolve()
    const next = previous.catch(() => undefined).then(async () => {
      const connection = await this.hocuspocus.openDirectConnection(docId, SERVICE_CONTEXT)
      let result!: T
      try {
        await connection.transact((document) => {
          result = fn(document)
        })
      } finally {
        await connection.disconnect({ unloadImmediately: immediate } as any)
      }
      return result
    })
    this.chains.set(docId, next)
    const cleanup = () => {
      if (this.chains.get(docId) === next) this.chains.delete(docId)
    }
    next.then(cleanup, cleanup)
    return next
  }

  read(docId: string): Promise<PMNode> {
    return this.run(docId, readDoc)
  }

  // Replace the whole document with `doc`; only the difference reaches the Y tree.
  replace(docId: string, doc: PMNode, { immediate = true } = {}): Promise<void> {
    return this.run(docId, (ydoc) => writeDoc(ydoc, doc), { immediate })
  }
}
