// The one Tiptap extension list for Blackboard documents. The document service and the browser
// editor both import this file, so both read and write the Yjs data with the same schema: reading
// Y data that does not fit the schema deletes the offending element.
import { Mark, getSchema, type AnyExtension } from '@tiptap/core'
import StarterKit from '@tiptap/starter-kit'
import Document from '@tiptap/extension-document'
import Blockquote from '@tiptap/extension-blockquote'
import CodeBlock from '@tiptap/extension-code-block'
import Paragraph from '@tiptap/extension-paragraph'
import Code from '@tiptap/extension-code'
import Heading from '@tiptap/extension-heading'
import HardBreak from '@tiptap/extension-hard-break'
import { BulletList, OrderedList, ListItem, TaskList, TaskItem } from '@tiptap/extension-list'
import { Table, TableRow, TableHeader, TableCell, renderTableToMarkdown } from '@tiptap/extension-table'
import Image from '@tiptap/extension-image'
import UniqueID from '@tiptap/extension-unique-id'
import type { Schema } from '@tiptap/pm/model'
import { deletion, insertion, modification } from '@handlewithcare/prosemirror-suggest-changes'
import { BREAK, HtmlBreak, PIPE, escapeLineStarts, guarded, tableStart } from './markdownFixes.ts'

// The Yjs XML fragment that holds a document, in the service and in the browser.
export const YJS_FIELD = 'default'

export const SUGGESTION_MARKS = 'insertion deletion modification'
export const SUGGESTION_TYPES = ['insertion', 'deletion', 'modification']

// Block types that get a stable id. Only top-level ids are used; nested paragraphs get one too,
// because UniqueID works per node type, not per depth.
export const BLOCK_ID_TYPES = [
  'paragraph', 'heading', 'bulletList', 'orderedList', 'taskList', 'blockquote',
  'codeBlock', 'table', 'horizontalRule', 'image',
]

let idCounter = 0
export function newBlockId(): string {
  idCounter += 1
  return 'b' + Date.now().toString(36) + idCounter.toString(36) + Math.random().toString(36).slice(2, 6)
}

// Authors are shown in one of this many colors (the browser's avatar palette).
export const AUTHOR_COLORS = 6
// An agent's text has its owner's id, so it takes another color than the owner's own text.
export function authorColorIndex(id: string, kind?: string): number {
  let hash = 0
  for (let i = 0; i < id.length; i += 1) hash = (hash * 31 + id.charCodeAt(i)) >>> 0
  return ((hash + (kind === 'agent' ? AUTHOR_COLORS / 2 : 0)) % AUTHOR_COLORS) + 1
}

// Who wrote a range of text: one author per character (default `excludes`). With `excludes: ''`
// y-tiptap would store the mark under hashed keys, which the author guard would have to parse.
export const AuthorMark = Mark.create({
  name: 'author',
  inclusive: false,
  addAttributes() {
    return {
      id: { default: null, parseHTML: (el: HTMLElement) => el.getAttribute('data-author'), renderHTML: (a: any) => (a.id ? { 'data-author': a.id, 'data-author-color': authorColorIndex(a.id, a.kind) } : {}) },
      kind: { default: 'person', parseHTML: (el: HTMLElement) => el.getAttribute('data-author-kind'), renderHTML: (a: any) => ({ 'data-author-kind': a.kind }) },
      mandate: { default: null, parseHTML: (el: HTMLElement) => el.getAttribute('data-mandate'), renderHTML: (a: any) => (a.mandate ? { 'data-mandate': a.mandate } : {}) },
    }
  },
  parseHTML() {
    return [{ tag: 'span[data-author]' }]
  },
  renderHTML({ HTMLAttributes }) {
    return ['span', HTMLAttributes, 0]
  },
})

// The prosemirror-suggest-changes marks, with an `author: {id, kind, mandate?}` attribute. The
// browser only renders them in this milestone; accepting and rejecting arrives in milestone 4.
function suggestionMark(spec: { excludes?: string }, name: string, extra: Record<string, unknown> = {}) {
  return Mark.create({
    name,
    inclusive: false,
    excludes: spec.excludes,
    addAttributes() {
      return {
        id: {
          default: null,
          parseHTML: (el: HTMLElement) => (el.dataset.id ? JSON.parse(el.dataset.id) : null),
          renderHTML: (a: any) => ({ 'data-id': JSON.stringify(a.id) }),
        },
        author: {
          default: null,
          parseHTML: (el: HTMLElement) => (el.dataset.author ? JSON.parse(el.dataset.author) : null),
          renderHTML: (a: any) => (a.author ? { 'data-author': JSON.stringify(a.author) } : {}),
        },
        ...extra,
      }
    },
    parseHTML() {
      return name === 'modification' ? [{ tag: "span[data-type='modification']" }] : [{ tag: name === 'insertion' ? 'ins' : 'del' }]
    },
    renderHTML({ HTMLAttributes }) {
      if (name === 'modification') return ['span', { ...HTMLAttributes, 'data-type': 'modification' }, 0]
      return [name === 'insertion' ? 'ins' : 'del', HTMLAttributes, 0]
    },
  })
}

export const Insertion = suggestionMark(insertion, 'insertion')
export const Deletion = suggestionMark(deletion, 'deletion')
export const Modification = suggestionMark(modification, 'modification', {
  type: { default: null },
  attrName: { default: null },
  previousValue: { default: null },
  newValue: { default: null },
})

// Container nodes must allow the suggestion marks on their children, or whole-block suggestions
// (node marks) are dropped by ProseMirror.
const allow = { marks: SUGGESTION_MARKS }

const BbParagraph = Paragraph.extend({
  renderMarkdown(node: any, h: any, ctx: any) {
    // A hard break at the very end has no Markdown form; left in, it comes back as a literal backslash.
    return escapeLineStarts((this as any).parent(node, h, ctx).replace(/(?:\\\n)+$/, ''))
  },
} as any)

const BbHeading = Heading.extend({
  renderMarkdown(node: any, h: any, ctx: any) {
    const level = node.attrs?.level ? parseInt(node.attrs.level, 10) : 1
    if (!node.content || !node.content.length) return '#'.repeat(level)
    // A trailing " #" would be read as a closing sequence and dropped.
    return (this as any).parent(node, h, ctx).replace(/([ \t])(#+)[ \t]*$/, '$1\\$2')
  },
} as any)

// A backslash break stays visible and survives an agent that trims trailing spaces.
const BbHardBreak = HardBreak.extend({ renderMarkdown: () => '\\\n' } as any)

// Tiptap's code mark excludes every other mark ('_'), so inline code could hold neither an author
// nor a suggestion mark, and a linked code span was invalid. It excludes formatting marks only.
const BbCode = Code.extend({ excludes: 'bold italic strike underline' })

const BbCodeBlock = CodeBlock.extend({
  marks: SUGGESTION_MARKS + ' author',
  // The fence must be longer than any backtick run inside the code.
  renderMarkdown(node: any) {
    const text = (node.content || []).map((c: any) => c.text || '').join('')
    const longest = Math.max(0, ...(text.match(/`+/g) || []).map((s: string) => s.length))
    const fence = '`'.repeat(Math.max(3, longest + 1))
    return `${fence}${node.attrs?.language || ''}\n${text}\n${fence}`
  },
} as any)

const BbOrderedList = OrderedList.extend({
  ...allow,
  markdownTokenizer: guarded((OrderedList.config as any).markdownTokenizer, /^\s*\d{1,9}[.)]/),
} as any)

const BbTaskList = TaskList.extend({
  ...allow,
  markdownTokenizer: guarded((TaskList.config as any).markdownTokenizer, /^\s*[-+*]\s+\[[ xX]\]/),
} as any)

const BbTable = Table.extend({
  ...allow,
  markdownTokenizer: { ...(Table.config as any).markdownTokenizer, start: tableStart },
  renderMarkdown(node: any, h: any) {
    const prep = (n: any): any => {
      if (n.type === 'text') return { ...n, text: n.text.split('|').join(PIPE) }
      if (n.type === 'hardBreak') return { type: 'text', text: BREAK }
      return n.content ? { ...n, content: n.content.map(prep) } : n
    }
    return renderTableToMarkdown(prep(node), h).split(PIPE).join('\\|').split(BREAK).join('<br>')
  },
} as any)

// Cells hold paragraphs only, so the editor cannot create content that a Markdown table cannot hold.
const cellContent = { ...allow, content: 'paragraph+' }

export interface ExtensionOptions {
  // Browser-only extensions such as Collaboration and CollaborationCaret.
  collaboration?: AnyExtension[]
}

export function blackboardExtensions({ collaboration = [] }: ExtensionOptions = {}): AnyExtension[] {
  return [
    StarterKit.configure({
      document: false,
      paragraph: false,
      heading: false,
      hardBreak: false,
      blockquote: false,
      codeBlock: false,
      code: false,
      bulletList: false,
      orderedList: false,
      listItem: false,
      undoRedo: false,
      trailingNode: false,
      link: { openOnClick: false },
    }),
    Document.extend(allow),
    BbParagraph,
    BbHeading,
    BbHardBreak,
    Blockquote.extend(allow),
    BbCodeBlock,
    BbCode,
    BulletList.extend(allow),
    BbOrderedList,
    ListItem.extend(allow),
    BbTaskList,
    TaskItem.extend(allow).configure({ nested: true }),
    BbTable,
    TableRow.extend(allow),
    TableHeader.extend(cellContent),
    TableCell.extend(cellContent),
    Image,
    UniqueID.configure({
      attributeName: 'id',
      types: BLOCK_ID_TYPES,
      generateID: () => newBlockId(),
      // Blocks that arrive from other people already have their ids.
      filterTransaction: (tr: any) => !tr.getMeta('y-sync$')?.isChangeOrigin,
    }),
    AuthorMark,
    Insertion,
    Deletion,
    Modification,
    HtmlBreak,
    ...collaboration,
  ]
}

let cachedSchema: Schema | null = null
export function blackboardSchema(): Schema {
  if (!cachedSchema) cachedSchema = getSchema(blackboardExtensions())
  return cachedSchema
}
