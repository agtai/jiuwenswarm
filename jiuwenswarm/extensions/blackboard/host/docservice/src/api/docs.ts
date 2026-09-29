// Routes for documents: create, delete, agent view, import, presence, token recheck.
import type { Hocuspocus } from '@hocuspocus/server'
import type { Node as PMNode } from '@tiptap/pm/model'
import { applySuggestion, revertSuggestion } from '@handlewithcare/prosemirror-suggest-changes'
import { EditorState } from '@tiptap/pm/state'
import * as Y from 'yjs'
import { ROLES, WRITE_ROLES } from '../auth.ts'
import { blackboardSchema } from '../schema/extensions.ts'
import { readAnchors, resolveAnchors } from '../docs/anchors.ts'
import { EditError, planEdit, readOps, type EditRequest } from '../docs/edits.ts'
import { MarkdownError, agentView, hasRawHtml, importDoc, type View } from '../docs/markdown.ts'
import { FIELD, readDoc, writeDoc, type DocPool } from '../docs/pool.ts'
import { suggestionsIn, type SuggestionSummary } from '../docs/suggestions.ts'
import type { DocStorage } from '../storage.ts'
import { ApiError, type Route } from './http.ts'

const DOC_ID = '([A-Za-z0-9_-]{1,64})'

export interface Author {
  id: string
  kind: 'person' | 'agent'
  mandate?: string | null
}

function readAuthor(value: any): Author {
  if (!value || typeof value.id !== 'string' || !value.id || !['person', 'agent'].includes(value.kind)) {
    throw new ApiError(400, 'invalid', 'author must be {id, kind: person | agent}', { field: 'author' })
  }
  return { id: value.id, kind: value.kind, mandate: typeof value.mandate === 'string' ? value.mandate : null }
}

function readMarkdown(value: unknown, required: boolean): string | null {
  if (value === undefined || value === null) {
    if (required) throw new ApiError(400, 'invalid', 'markdown is required', { field: 'markdown' })
    return null
  }
  if (typeof value !== 'string') throw new ApiError(400, 'invalid', 'markdown must be a string', { field: 'markdown' })
  return value
}

// Every piece of text in `doc` gets `author`, as one normal (non-suggestion) change.
function withAuthor(doc: PMNode, author: Author): PMNode {
  const schema = blackboardSchema()
  const mark = schema.marks.author.create({ id: author.id, kind: author.kind, mandate: author.mandate ?? null })
  const json = doc.toJSON()
  const walk = (node: any): any => {
    if (node.type === 'text') {
      const marks = (node.marks || []).filter((m: any) => m.type !== 'author')
      return { ...node, marks: [...marks, mark.toJSON()] }
    }
    return node.content ? { ...node, content: node.content.map(walk) } : node
  }
  return schema.nodeFromJSON(walk(json))
}

function contentFor(markdown: string | null, author: Author): PMNode {
  try {
    return withAuthor(importDoc(markdown ?? ''), author)
  } catch (error) {
    throw new ApiError(400, 'unsupported_markdown', 'the Markdown does not parse into a valid document', {
      detail: error instanceof Error ? error.message : String(error),
    })
  }
}

function readAllowed(value: any): EditRequest['allowed'] {
  if (value === undefined || value === null) return null
  if (typeof value.blockFrom !== 'string' || typeof value.blockTo !== 'string') {
    throw new ApiError(400, 'invalid', 'allowed is {blockFrom, blockTo}', { field: 'allowed' })
  }
  return { blockFrom: value.blockFrom, blockTo: value.blockTo }
}

// A relative position at the start of a block's first text, or before the block when it has none.
function blockStart(ydoc: Y.Doc, blockId: string): unknown {
  const fragment = ydoc.getXmlFragment(FIELD)
  const blocks = fragment.toArray()
  const index = blocks.findIndex((b) => b instanceof Y.XmlElement && b.getAttribute('id') === blockId)
  if (index < 0) return null
  const firstText = (el: Y.XmlElement): Y.XmlText | null => {
    for (const child of el.toArray()) {
      if (child instanceof Y.XmlText) return child
      if (child instanceof Y.XmlElement) {
        const found = firstText(child)
        if (found) return found
      }
    }
    return null
  }
  const text = firstText(blocks[index] as Y.XmlElement)
  const position = text ? Y.createRelativePositionFromTypeIndex(text, 0) : Y.createRelativePositionFromTypeIndex(fragment, index)
  return Y.relativePositionToJSON(position)
}

export interface DocRoutesDeps {
  hocuspocus: Hocuspocus
  pool: DocPool
  storage: DocStorage
  version: string
  shutdown: () => void
}

export function docRoutes({ hocuspocus, pool, storage, version, shutdown }: DocRoutesDeps): Route[] {
  const requireDoc = (docId: string) => {
    if (!storage.exists(docId) && !hocuspocus.documents.has(docId)) {
      throw new ApiError(404, 'not_found', 'no such document', { doc_id: docId })
    }
  }
  const connectionsOf = (docId: string): any[] => hocuspocus.documents.get(docId)?.getConnections() ?? []

  return [
    {
      method: 'GET',
      path: /^\/api\/health$/,
      handler: async () => ({ ok: true, openDocuments: hocuspocus.getDocumentsCount(), version }),
    },
    {
      method: 'POST',
      path: /^\/api\/docs$/,
      handler: async ({ body }) => {
        const docId = typeof body.docId === 'string' ? body.docId : ''
        if (!new RegExp(`^${DOC_ID}$`).test(docId)) throw new ApiError(400, 'invalid', 'docId is required', { field: 'docId' })
        if (storage.exists(docId)) throw new ApiError(409, 'conflict', 'the document already exists', { doc_id: docId })
        const markdown = readMarkdown(body.markdown, false)
        const doc = contentFor(markdown, readAuthor(body.author))
        storage.revive(docId)
        await pool.replace(docId, doc, { immediate: true })
        return { docId, rawHtml: markdown ? hasRawHtml(markdown) : false }
      },
    },
    {
      method: 'DELETE',
      path: new RegExp(`^/api/docs/${DOC_ID}$`),
      handler: async ({ params: [docId] }) => {
        // Delete first, so the save a closing connection attempts is ignored.
        storage.delete(docId)
        hocuspocus.closeConnections(docId)
        const loaded = hocuspocus.documents.get(docId)
        if (loaded) await hocuspocus.unloadDocument(loaded)
        return { docId, deleted: true }
      },
    },
    {
      method: 'GET',
      path: new RegExp(`^/api/docs/${DOC_ID}/markdown$`),
      handler: async ({ params: [docId], query }) => {
        requireDoc(docId)
        const view = (query.get('view') || 'accepted') as View
        if (view !== 'accepted' && view !== 'proposed') throw new ApiError(400, 'invalid', 'view is accepted or proposed', { field: 'view' })
        const doc = await pool.read(docId)
        try {
          return agentView(doc, { view, range: query.get('range') })
        } catch (error) {
          if (error instanceof MarkdownError) throw new ApiError(400, error.code, error.message, error.details)
          throw error
        }
      },
    },
    {
      method: 'POST',
      path: new RegExp(`^/api/docs/${DOC_ID}/import$`),
      handler: async ({ params: [docId], body }) => {
        requireDoc(docId)
        const markdown = readMarkdown(body.markdown, true) as string
        const doc = contentFor(markdown, readAuthor(body.author))
        await pool.replace(docId, doc, { immediate: true })
        return { ...agentView(doc), rawHtml: hasRawHtml(markdown) }
      },
    },
    {
      method: 'GET',
      path: new RegExp(`^/api/docs/${DOC_ID}/presence$`),
      handler: async ({ params: [docId] }) => ({
        connections: connectionsOf(docId).map((c) => ({
          userId: c.context?.userId ?? null,
          kind: c.context?.kind ?? null,
          readOnly: Boolean(c.readOnly),
        })),
      }),
    },
    {
      method: 'POST',
      path: new RegExp(`^/api/docs/${DOC_ID}/recheck$`),
      // The host is the authority on roles: for one person, `role` applies at once and `revoke`
      // closes their connections, and both outrank tokens minted earlier. Otherwise the browsers
      // show a fresh token.
      handler: async ({ params: [docId], body }) => {
        const userId = typeof body.userId === 'string' ? body.userId : null
        const role = ROLES.includes(body.role) ? (body.role as string) : null
        if (userId && (role || body.revoke === true)) {
          storage.setAccess(docId, userId, body.revoke === true ? null : role, Math.floor(Date.now() / 1000))
        }
        const matching = connectionsOf(docId).filter((c) => !userId || c.context?.userId === userId)
        for (const connection of matching) {
          if (body.revoke === true) {
            connection.close({ code: 4403, reason: 'access_revoked' })
            continue
          }
          if (role) {
            connection.readOnly = !WRITE_ROLES.includes(role)
            connection.context.role = role
          }
          connection.requestToken()
        }
        return { rechecked: matching.length }
      },
    },
    {
      method: 'POST',
      path: new RegExp(`^/api/docs/${DOC_ID}/edits$`),
      handler: async ({ params: [docId], body }) => {
        requireDoc(docId)
        const author = readAuthor(body.author)
        if (author.kind !== 'agent') throw new ApiError(400, 'invalid', 'edits are written by an agent', { field: 'author' })
        const req: EditRequest = {
          mandateId: typeof body.mandateId === 'string' ? body.mandateId : null,
          author: { ...author, mandate: typeof body.mandateId === 'string' ? body.mandateId : null },
          mode: body.mode === 'direct' ? 'direct' : 'suggest',
          allowed: readAllowed(body.allowed),
          ops: [],
        }
        try {
          req.ops = readOps(body.ops)
          return await pool.run(
            docId,
            (ydoc) => {
              const { doc, result } = planEdit(readDoc(ydoc), req)
              if (result.changed) writeDoc(ydoc, doc)
              return result
            },
            { immediate: true },
          )
        } catch (error) {
          if (error instanceof EditError) throw new ApiError(409, error.code, error.message, error.details)
          throw error
        }
      },
    },
    {
      // Comment anchors against the live document: ok, drifted, orphaned, or moved (new positions).
      method: 'POST',
      path: new RegExp(`^/api/docs/${DOC_ID}/anchors/resolve$`),
      handler: async ({ params: [docId], body }) => {
        requireDoc(docId)
        let anchors
        try {
          anchors = readAnchors(body.anchors)
        } catch (error) {
          throw new ApiError(400, 'invalid', error instanceof Error ? error.message : String(error), { field: 'anchors' })
        }
        return { anchors: await pool.run(docId, (ydoc) => resolveAnchors(ydoc, anchors)) }
      },
    },
    {
      method: 'GET',
      path: new RegExp(`^/api/docs/${DOC_ID}/suggestions$`),
      handler: async ({ params: [docId] }) => {
        requireDoc(docId)
        const doc = await pool.read(docId)
        const byId = new Map<string, SuggestionSummary & { blockIds: string[] }>()
        doc.forEach((node, offset) => {
          for (const s of suggestionsIn(doc, offset, offset + node.nodeSize)) {
            const entry = byId.get(s.id) ?? { ...s, inserted: '', deleted: '', blockIds: [] }
            entry.inserted += s.inserted
            entry.deleted += s.deleted
            if (node.attrs.id) entry.blockIds.push(node.attrs.id)
            byId.set(s.id, entry)
          }
        })
        return { suggestions: [...byId.values()] }
      },
    },
    {
      method: 'POST',
      path: new RegExp(`^/api/docs/${DOC_ID}/suggestions/([A-Za-z0-9_-]{1,64})$`),
      handler: async ({ params: [docId, suggestionId], body }) => {
        requireDoc(docId)
        const action = body.action
        if (action !== 'accept' && action !== 'reject') throw new ApiError(400, 'invalid', 'action is accept or reject', { field: 'action' })
        const decided = await pool.run(
          docId,
          (ydoc) => {
            const doc = readDoc(ydoc)
            if (!suggestionsIn(doc).some((s) => s.id === suggestionId)) return false
            let state = EditorState.create({ schema: blackboardSchema(), doc })
            const command = action === 'accept' ? applySuggestion(suggestionId) : revertSuggestion(suggestionId)
            command(state, (tr) => {
              state = state.apply(tr)
            })
            writeDoc(ydoc, state.doc)
            return true
          },
          { immediate: true },
        )
        if (!decided) throw new ApiError(404, 'not_found', 'no pending suggestion has this id', { suggestion_id: suggestionId })
        return { suggestionId, action }
      },
    },
    {
      method: 'POST',
      path: new RegExp(`^/api/docs/${DOC_ID}/presence$`),
      // An agent's caret for the people with the document open. Only one agent writes a document at
      // a time (the host's lock), so the service's own awareness state carries it.
      handler: async ({ params: [docId], body }) => {
        const document = hocuspocus.documents.get(docId)
        if (!document) return { shown: false }
        if (body.status === null || body.status === undefined) {
          document.awareness.setLocalState(null)
          return { shown: false }
        }
        if (typeof body.agentId !== 'string' || typeof body.label !== 'string' || !['reading', 'writing'].includes(body.status)) {
          throw new ApiError(400, 'invalid', 'presence is {agentId, label, status: reading | writing, blockId?}')
        }
        const at = typeof body.blockId === 'string' ? blockStart(document, body.blockId) : null
        document.awareness.setLocalState({
          user: { id: `agent:${body.agentId}`, name: body.label, kind: 'agent', status: body.status },
          cursor: at ? { anchor: at, head: at } : null,
        })
        return { shown: true }
      },
    },
    {
      method: 'POST',
      path: /^\/api\/shutdown$/,
      handler: async () => {
        setImmediate(shutdown)
        return { ok: true }
      },
    },
  ]
}
