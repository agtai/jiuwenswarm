// Routes for a document's history (list, one version, diff, save, restore) and its exports.
import type { Hocuspocus } from '@hocuspocus/server'
import type { Node as PMNode } from '@tiptap/pm/model'
import { diffDocs } from '../docs/diff.ts'
import { CONTENT_TYPES, ExportError, exportDocx, exportMarkdown, exportPdf, findChromium, type ExportDecision, type ExportFormat } from '../docs/export.ts'
import { serializeMarkdown, viewJSON } from '../docs/markdown.ts'
import { readDoc, writeDoc, type DocPool } from '../docs/pool.ts'
import type { VersionAuthor, Versions } from '../docs/versions.ts'
import type { DocStorage } from '../storage.ts'
import { ApiError, type Route } from './http.ts'

const DOC_ID = '([A-Za-z0-9_-]{1,64})'
const VERSION_ID = '([A-Za-z0-9_-]{1,64})'
const MAX_PAGE = 200
const MAX_LABEL = 200

export function readVersionAuthor(value: any): VersionAuthor {
  if (!value || typeof value.id !== 'string' || !value.id || !['person', 'agent'].includes(value.kind)) {
    throw new ApiError(400, 'invalid', 'author must be {id, kind: person | agent}', { field: 'author' })
  }
  return { id: value.id, kind: value.kind }
}

function readDecisions(value: unknown): ExportDecision[] {
  if (value === undefined || value === null) return []
  if (!Array.isArray(value) || value.length > 500) throw new ApiError(400, 'invalid', 'decisions is a list', { field: 'decisions' })
  const text = (v: unknown) => (typeof v === 'string' ? v : '')
  return value.map((d: any) => ({
    question: text(d?.question),
    answer: text(d?.answer),
    answeredBy: text(d?.answeredBy),
    acceptedBy: typeof d?.acceptedBy === 'string' ? d.acceptedBy : null,
  }))
}

// Characters that are not allowed in file names on some systems become a space.
export function fileName(title: string, ext: string): string {
  const base = title.replace(/[\\/:*?"<>|\x00-\x1f]+/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 120) || 'document'
  return `${base}.${ext}`
}

export interface VersionRoutesDeps {
  hocuspocus: Hocuspocus
  pool: DocPool
  storage: DocStorage
  versions: Versions
  chromium: string | null
}

export function versionRoutes({ hocuspocus, pool, storage, versions, chromium }: VersionRoutesDeps): Route[] {
  const requireDoc = (docId: string) => {
    if (!storage.exists(docId) && !hocuspocus.documents.has(docId)) {
      throw new ApiError(404, 'not_found', 'no such document', { doc_id: docId })
    }
  }
  const load = (docId: string, versionId: string) => {
    const found = versions.load(docId, versionId)
    if (!found) throw new ApiError(404, 'not_found', 'no such version', { version_id: versionId })
    return found
  }

  return [
    {
      method: 'GET',
      path: new RegExp(`^/api/docs/${DOC_ID}/versions$`),
      handler: async ({ params: [docId], query }) => {
        requireDoc(docId)
        const limit = Math.min(MAX_PAGE, Math.max(1, Number(query.get('limit')) || 50))
        const page = versions.list(docId, limit + 1, query.get('before'))
        return { versions: page.slice(0, limit), hasMore: page.length > limit }
      },
    },
    {
      // A named version of the document as it is now.
      method: 'POST',
      path: new RegExp(`^/api/docs/${DOC_ID}/versions$`),
      handler: async ({ params: [docId], body }) => {
        requireDoc(docId)
        const author = readVersionAuthor(body.author)
        const label = typeof body.label === 'string' ? body.label.trim().slice(0, MAX_LABEL) || null : null
        await versions.flush(docId)
        const doc = await pool.read(docId)
        return { version: versions.record(docId, doc, { reason: 'manual', authors: [author], label, force: true }) }
      },
    },
    {
      // One version: its ProseMirror JSON (suggestions and authors included), or its accepted Markdown.
      method: 'GET',
      path: new RegExp(`^/api/docs/${DOC_ID}/versions/${VERSION_ID}$`),
      handler: async ({ params: [docId, versionId], query }) => {
        const { info, doc } = load(docId, versionId)
        if (query.get('format') === 'markdown') {
          return { version: info, markdown: serializeMarkdown(viewJSON(doc.toJSON() as any, 'accepted') ?? { type: 'doc', content: [] }) }
        }
        return { version: info, previous: versions.previous(docId, versionId), doc: doc.toJSON() }
      },
    },
    {
      // What changed from one version to another; without `from`, since the version before `to`.
      method: 'GET',
      path: new RegExp(`^/api/docs/${DOC_ID}/diff$`),
      handler: async ({ params: [docId], query }) => {
        const to = query.get('to')
        if (!to) throw new ApiError(400, 'invalid', 'to is a version id', { field: 'to' })
        const target = load(docId, to)
        const from = query.get('from') ?? versions.previous(docId, to)
        const base: PMNode | null = from ? load(docId, from).doc : null
        return { from, to, ...diffDocs(base, target.doc) }
      },
    },
    {
      // The document becomes the version again, suggestions and authors as they were; the restore
      // itself is a new version credited to the person who restored.
      method: 'POST',
      path: new RegExp(`^/api/docs/${DOC_ID}/restore$`),
      handler: async ({ params: [docId], body }) => {
        requireDoc(docId)
        const author = readVersionAuthor(body.author)
        const versionId = typeof body.versionId === 'string' ? body.versionId : ''
        const { doc } = load(docId, versionId)
        await versions.flush(docId)
        const version = await pool.run(
          docId,
          (ydoc) => {
            writeDoc(ydoc, doc)
            return versions.record(docId, readDoc(ydoc), { reason: 'restore', authors: [author], restoredFrom: versionId, force: true })
          },
          { immediate: true },
        )
        return { version }
      },
    },
    {
      // The accepted view (or a version's) as a file, returned as base64 for the host to serve.
      method: 'POST',
      path: new RegExp(`^/api/docs/${DOC_ID}/export$`),
      handler: async ({ params: [docId], body }) => {
        requireDoc(docId)
        const format = body.format as ExportFormat
        if (!['md', 'docx', 'pdf'].includes(format)) throw new ApiError(400, 'unsupported_format', 'format is md, docx or pdf', { field: 'format' })
        const title = typeof body.title === 'string' && body.title.trim() ? body.title.trim() : 'Document'
        const options = { title, decisions: readDecisions(body.decisions) }
        const doc = typeof body.versionId === 'string' ? load(docId, body.versionId).doc : await pool.read(docId)
        try {
          const data =
            format === 'md'
              ? Buffer.from(exportMarkdown(doc, options), 'utf8')
              : format === 'docx'
                ? await exportDocx(doc, options)
                : await exportPdf(doc, options, findChromium(chromium))
          return { fileName: fileName(title, format), contentType: CONTENT_TYPES[format], size: data.length, data: data.toString('base64') }
        } catch (error) {
          if (error instanceof ExportError) throw new ApiError(error.code === 'pdf_unavailable' ? 409 : 500, error.code, error.message)
          throw error
        }
      },
    },
  ]
}
