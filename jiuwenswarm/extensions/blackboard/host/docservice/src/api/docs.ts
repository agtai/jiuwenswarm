// Routes for documents: create, delete, agent view, import, presence, token recheck.
import type { Hocuspocus } from '@hocuspocus/server'
import type { Node as PMNode } from '@tiptap/pm/model'
import { ROLES, WRITE_ROLES } from '../auth.ts'
import { blackboardSchema } from '../schema/extensions.ts'
import { MarkdownError, agentView, hasRawHtml, importDoc, type View } from '../docs/markdown.ts'
import type { DocPool } from '../docs/pool.ts'
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
      path: /^\/api\/shutdown$/,
      handler: async () => {
        setImmediate(shutdown)
        return { ok: true }
      },
    },
  ]
}
