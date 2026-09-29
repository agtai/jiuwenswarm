// Exports of a document's accepted view (pending suggestions left out): Markdown, Word (.docx) and
// PDF, each optionally with the decisions about the document appended as a table. PDF is printed by
// a local Chrome, Edge or Chromium in headless mode from an HTML rendering of the Markdown.
import { spawn } from 'node:child_process'
import { existsSync, mkdtempSync, readFileSync, readdirSync, rmSync, writeFileSync } from 'node:fs'
import { homedir, tmpdir } from 'node:os'
import { delimiter, join } from 'node:path'
import { pathToFileURL } from 'node:url'
import {
  AlignmentType,
  BorderStyle,
  Document,
  ExternalHyperlink,
  HeadingLevel,
  ImageRun,
  LevelFormat,
  Packer,
  Paragraph,
  ShadingType,
  Table,
  TableCell,
  TableRow,
  TextRun,
  WidthType,
} from 'docx'
import { Marked } from 'marked'
import type { Node as PMNode } from '@tiptap/pm/model'
import { serializeMarkdown, viewJSON } from './markdown.ts'

type Json = { type: string; attrs?: Record<string, any>; content?: Json[]; marks?: { type: string; attrs?: any }[]; text?: string }

export type ExportFormat = 'md' | 'docx' | 'pdf'

export const CONTENT_TYPES: Record<ExportFormat, string> = {
  md: 'text/markdown; charset=utf-8',
  docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  pdf: 'application/pdf',
}

export interface ExportDecision {
  question: string
  answer: string
  answeredBy: string
  acceptedBy: string | null
}

export interface ExportOptions {
  title: string
  decisions: ExportDecision[]
}

export class ExportError extends Error {
  code: string
  constructor(code: string, message: string) {
    super(message)
    this.code = code
  }
}

const DECISION_HEADERS = ['Question', 'Answer', 'Answered by', 'Accepted by']

function acceptedJson(doc: PMNode): Json {
  return viewJSON(doc.toJSON() as Json, 'accepted') ?? { type: 'doc', content: [] }
}

function decisionRow(d: ExportDecision): string[] {
  return [d.question, d.answer, d.answeredBy, d.acceptedBy ?? '']
}

// ---- Markdown ----

function markdownCell(text: string): string {
  return text.replace(/\|/g, '\\|').replace(/\s*\n\s*/g, ' ').trim()
}

function decisionsMarkdown(decisions: ExportDecision[]): string {
  const row = (cells: string[]) => `| ${cells.map(markdownCell).join(' | ')} |`
  return ['## Decisions', '', row(DECISION_HEADERS), `|${' --- |'.repeat(DECISION_HEADERS.length)}`, ...decisions.map((d) => row(decisionRow(d))), ''].join('\n')
}

export function exportMarkdown(doc: PMNode, { decisions }: ExportOptions): string {
  const body = serializeMarkdown(acceptedJson(doc)).trimEnd()
  return decisions.length ? `${body}\n\n${decisionsMarkdown(decisions)}` : `${body}\n`
}

// ---- Word ----

interface Picture {
  type: 'png' | 'jpg' | 'gif' | 'bmp'
  data: Buffer
  width: number
  height: number
}

const MONO = 'Consolas'
const MAX_IMAGE_BYTES = 10 * 1024 * 1024
const MAX_IMAGE_WIDTH = 600
const HEADINGS = [HeadingLevel.HEADING_1, HeadingLevel.HEADING_2, HeadingLevel.HEADING_3, HeadingLevel.HEADING_4, HeadingLevel.HEADING_5, HeadingLevel.HEADING_6]

// The format and pixel size from the file's header; null for anything Word cannot take as is.
export function pictureOf(data: Buffer): Picture | null {
  if (data.length > 24 && data.readUInt32BE(0) === 0x89504e47) return { type: 'png', data, width: data.readUInt32BE(16), height: data.readUInt32BE(20) }
  if (data.length > 10 && data.toString('ascii', 0, 4) === 'GIF8') return { type: 'gif', data, width: data.readUInt16LE(6), height: data.readUInt16LE(8) }
  if (data.length > 26 && data.toString('ascii', 0, 2) === 'BM') return { type: 'bmp', data, width: data.readInt32LE(18), height: Math.abs(data.readInt32LE(22)) }
  if (data.length > 4 && data[0] === 0xff && data[1] === 0xd8) {
    let at = 2
    while (at + 9 < data.length && data[at] === 0xff) {
      const marker = data[at + 1]
      const length = data.readUInt16BE(at + 2)
      if (marker >= 0xc0 && marker <= 0xcf && ![0xc4, 0xc8, 0xcc].includes(marker)) {
        return { type: 'jpg', data, width: data.readUInt16BE(at + 7), height: data.readUInt16BE(at + 5) }
      }
      at += 2 + length
    }
  }
  return null
}

async function fetchPicture(src: string): Promise<Picture | null> {
  try {
    if (src.startsWith('data:')) {
      const comma = src.indexOf(',')
      return comma > 0 && src.slice(0, comma).includes(';base64') ? pictureOf(Buffer.from(src.slice(comma + 1), 'base64')) : null
    }
    if (!/^https?:\/\//i.test(src)) return null
    const response = await fetch(src, { signal: AbortSignal.timeout(10000) })
    if (!response.ok) return null
    const data = Buffer.from(await response.arrayBuffer())
    return data.length <= MAX_IMAGE_BYTES ? pictureOf(data) : null
  } catch {
    return null
  }
}

function imageSources(node: Json, out: Set<string>): Set<string> {
  if (node.type === 'image' && typeof node.attrs?.src === 'string') out.add(node.attrs.src)
  for (const child of node.content ?? []) imageSources(child, out)
  return out
}

const isWebLink = (href: unknown): href is string => typeof href === 'string' && /^(https?:|mailto:)/i.test(href)

type Inline = TextRun | ExternalHyperlink

function runs(nodes: Json[] | undefined, base: { bold?: boolean } = {}): Inline[] {
  const out: Inline[] = []
  for (const node of nodes ?? []) {
    if (node.type === 'text') {
      const has = (name: string) => (node.marks ?? []).some((m) => m.type === name)
      const link = (node.marks ?? []).find((m) => m.type === 'link')?.attrs?.href
      const run = new TextRun({
        text: node.text ?? '',
        bold: has('bold') || base.bold,
        italics: has('italic'),
        strike: has('strike'),
        underline: has('underline') ? {} : undefined,
        font: has('code') ? MONO : undefined,
        style: isWebLink(link) ? 'Hyperlink' : undefined,
      })
      out.push(isWebLink(link) ? new ExternalHyperlink({ link, children: [run] }) : run)
    } else if (node.type === 'hardBreak') {
      out.push(new TextRun({ break: 1 }))
    } else if (node.content) {
      out.push(...runs(node.content, base))
    }
  }
  return out
}

interface WordContext {
  pictures: Map<string, Picture | null>
  lists: number
}

const QUOTE = { indent: { left: 540 }, border: { left: { style: BorderStyle.SINGLE, size: 12, color: 'BBBBBB', space: 10 } } }

function imageBlock(node: Json, ctx: WordContext): Paragraph {
  const src = String(node.attrs?.src ?? '')
  const picture = ctx.pictures.get(src)
  if (picture && picture.width > 0 && picture.height > 0) {
    const scale = Math.min(1, MAX_IMAGE_WIDTH / picture.width)
    return new Paragraph({
      children: [
        new ImageRun({ type: picture.type, data: picture.data, transformation: { width: Math.round(picture.width * scale), height: Math.round(picture.height * scale) } }),
      ],
    })
  }
  const label = new TextRun({ text: String(node.attrs?.alt || src), style: isWebLink(src) ? 'Hyperlink' : undefined })
  return new Paragraph({ children: [isWebLink(src) ? new ExternalHyperlink({ link: src, children: [label] }) : label] })
}

function tableBlock(node: Json): Table {
  const rows = (node.content ?? []).map((row) => {
    const header = (row.content ?? []).every((cell) => cell.type === 'tableHeader')
    return new TableRow({
      tableHeader: header,
      children: (row.content ?? []).map((cell) => {
        const paragraphs = (cell.content ?? []).map((p) => new Paragraph({ children: runs(p.content, { bold: cell.type === 'tableHeader' }) }))
        return new TableCell({ children: paragraphs.length ? paragraphs : [new Paragraph('')] })
      }),
    })
  })
  return new Table({ rows, width: { size: 100, type: WidthType.PERCENTAGE } })
}

function listBlocks(list: Json, ctx: WordContext, level: number): Array<Paragraph | Table> {
  const out: Array<Paragraph | Table> = []
  const depth = Math.min(level, 8)
  const instance = list.type === 'orderedList' ? ++ctx.lists : 0
  for (const item of list.content ?? []) {
    const [first, ...rest] = item.content ?? []
    const prefix = list.type === 'taskList' ? [new TextRun({ text: item.attrs?.checked ? '[x] ' : '[ ] ' })] : []
    const marker = list.type === 'orderedList' ? { numbering: { reference: 'bb-ordered', level: depth, instance } } : { bullet: { level: depth } }
    out.push(new Paragraph({ ...marker, children: [...prefix, ...runs(first?.type === 'paragraph' ? first.content : [])] }))
    const more = first && first.type !== 'paragraph' ? [first, ...rest] : rest
    for (const child of more) {
      if (child.type === 'paragraph') out.push(new Paragraph({ indent: { left: 720 * (depth + 1) }, children: runs(child.content) }))
      else out.push(...wordBlocks([child], ctx, level + 1))
    }
  }
  return out
}

function wordBlocks(nodes: Json[] | undefined, ctx: WordContext, level = 0, quoted = false): Array<Paragraph | Table> {
  const out: Array<Paragraph | Table> = []
  for (const node of nodes ?? []) {
    switch (node.type) {
      case 'paragraph':
        out.push(new Paragraph({ ...(quoted ? QUOTE : {}), children: runs(node.content) }))
        break
      case 'heading':
        out.push(new Paragraph({ heading: HEADINGS[Math.min(6, Math.max(1, Number(node.attrs?.level) || 1)) - 1], children: runs(node.content) }))
        break
      case 'blockquote':
        out.push(...wordBlocks(node.content, ctx, level, true))
        break
      case 'codeBlock': {
        const lines = (node.content ?? []).map((t) => t.text ?? '').join('').split('\n')
        out.push(
          new Paragraph({
            shading: { type: ShadingType.CLEAR, color: 'auto', fill: 'F3F4F6' },
            children: lines.map((line, i) => new TextRun({ text: line, font: MONO, break: i ? 1 : undefined })),
          }),
        )
        break
      }
      case 'bulletList':
      case 'orderedList':
      case 'taskList':
        out.push(...listBlocks(node, ctx, level))
        break
      case 'table':
        out.push(tableBlock(node))
        break
      case 'horizontalRule':
        out.push(new Paragraph({ border: { bottom: { style: BorderStyle.SINGLE, size: 6, color: 'BBBBBB', space: 1 } } }))
        break
      case 'image':
        out.push(imageBlock(node, ctx))
        break
      default:
        if (node.content) out.push(...wordBlocks(node.content, ctx, level, quoted))
    }
  }
  return out
}

function decisionsWord(decisions: ExportDecision[]): Array<Paragraph | Table> {
  const row = (cells: string[], header: boolean) =>
    new TableRow({
      tableHeader: header,
      children: cells.map((text) => new TableCell({ children: [new Paragraph({ children: [new TextRun({ text, bold: header })] })] })),
    })
  return [
    new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun('Decisions')] }),
    new Table({ rows: [row(DECISION_HEADERS, true), ...decisions.map((d) => row(decisionRow(d), false))], width: { size: 100, type: WidthType.PERCENTAGE } }),
  ]
}

export async function exportDocx(doc: PMNode, { title, decisions }: ExportOptions): Promise<Buffer> {
  const json = acceptedJson(doc)
  const pictures = new Map<string, Picture | null>()
  await Promise.all([...imageSources(json, new Set())].map(async (src) => pictures.set(src, await fetchPicture(src))))
  const body = wordBlocks(json.content, { pictures, lists: 0 })
  const document = new Document({
    title,
    creator: 'Blackboard',
    numbering: {
      config: [
        {
          reference: 'bb-ordered',
          levels: Array.from({ length: 9 }, (_, level) => ({
            level,
            format: LevelFormat.DECIMAL,
            text: `%${level + 1}.`,
            alignment: AlignmentType.START,
            style: { paragraph: { indent: { left: 720 * (level + 1), hanging: 360 } } },
          })),
        },
      ],
    },
    sections: [
      {
        children: [
          new Paragraph({ heading: HeadingLevel.TITLE, children: [new TextRun(title)] }),
          ...body,
          ...(decisions.length ? decisionsWord(decisions) : []),
        ],
      },
    ],
  })
  return Packer.toBuffer(document)
}

// ---- PDF ----

const PRINT_CSS = `
@page { size: A4; margin: 20mm 18mm 22mm; @bottom-center { content: counter(page) " / " counter(pages); font: 9pt sans-serif; color: #666; } }
body { font: 11pt/1.55 "Segoe UI", "Helvetica Neue", Arial, "Noto Sans", "PingFang SC", "Microsoft YaHei", sans-serif; color: #1a1a1a; margin: 0; }
.doc-title { font-size: 22pt; margin: 0 0 14pt; }
h1 { font-size: 17pt; } h2 { font-size: 14.5pt; } h3 { font-size: 12.5pt; }
h1, h2, h3, h4 { margin: 16pt 0 6pt; page-break-after: avoid; }
p, ul, ol, table, pre, blockquote { margin: 0 0 8pt; }
pre { padding: 8pt; border-radius: 4pt; background: #f4f4f5; white-space: pre-wrap; font: 9.5pt/1.45 Consolas, "Courier New", monospace; page-break-inside: avoid; }
code { font-family: Consolas, "Courier New", monospace; }
:not(pre) > code { padding: 0 2pt; border-radius: 2pt; background: #f4f4f5; }
blockquote { margin-left: 2pt; padding-left: 10pt; border-left: 3pt solid #d4d4d8; color: #52525b; }
table { width: 100%; border-collapse: collapse; }
th, td { padding: 4pt 6pt; border: 1px solid #d4d4d8; text-align: left; vertical-align: top; }
th { background: #f4f4f5; }
tr, img { page-break-inside: avoid; }
img { max-width: 100%; }
hr { border: 0; border-top: 1px solid #d4d4d8; }
a { color: #1d4ed8; }
li > input[type="checkbox"] { margin: 0 4pt 0 0; }
li:has(> input[type="checkbox"]) { list-style: none; }
`

const escapeHtml = (text: string) => text.replace(/[&<>"']/g, (c) => `&#${c.charCodeAt(0)};`)

// Raw HTML in a document is text, as in the editor, so it is escaped rather than rendered.
const printMarked = new Marked({ gfm: true, async: false })
printMarked.use({ renderer: { html: (token: any) => escapeHtml(String(token.text ?? token.raw ?? '')) } })

export function printHtml(doc: PMNode, { title, decisions }: ExportOptions): string {
  const body = printMarked.parse(exportMarkdown(doc, { title, decisions }), { async: false }) as string
  return [
    '<!doctype html><html><head><meta charset="utf-8">',
    `<meta http-equiv="Content-Security-Policy" content="default-src 'none'; img-src data: http: https:; style-src 'unsafe-inline'">`,
    `<title>${escapeHtml(title)}</title><style>${PRINT_CSS}</style></head>`,
    `<body><h1 class="doc-title">${escapeHtml(title)}</h1>${body}</body></html>`,
  ].join('')
}

// Chromium that a Playwright install downloaded, the newest first.
function playwrightChromium(): string[] {
  const roots = [
    process.env.PLAYWRIGHT_BROWSERS_PATH,
    process.env.LOCALAPPDATA && join(process.env.LOCALAPPDATA, 'ms-playwright'),
    join(homedir(), '.cache', 'ms-playwright'),
    join(homedir(), 'Library', 'Caches', 'ms-playwright'),
  ].filter((p): p is string => Boolean(p) && existsSync(p as string))
  const found: string[] = []
  for (const root of roots) {
    const builds = readdirSync(root).filter((d) => /^chromium-\d+$/.test(d)).sort((a, b) => Number(b.split('-')[1]) - Number(a.split('-')[1]))
    for (const build of builds) {
      found.push(
        join(root, build, 'chrome-win64', 'chrome.exe'),
        join(root, build, 'chrome-win', 'chrome.exe'),
        join(root, build, 'chrome-linux64', 'chrome'),
        join(root, build, 'chrome-linux', 'chrome'),
        join(root, build, 'chrome-mac', 'Chromium.app', 'Contents', 'MacOS', 'Chromium'),
      )
    }
  }
  return found
}

function onPath(names: string[]): string[] {
  return (process.env.PATH ?? '').split(delimiter).flatMap((dir) => names.map((name) => join(dir, name)))
}

// A browser that can print to PDF: the configured one, then Chrome, Edge and Chromium in their
// usual places, then a Playwright download.
export function findChromium(configured: string | null): string | null {
  const env = process.env
  const candidates: string[] = []
  if (configured) candidates.push(configured)
  if (process.platform === 'win32') {
    for (const base of [env.PROGRAMFILES, env['PROGRAMFILES(X86)'], env.LOCALAPPDATA]) {
      if (!base) continue
      candidates.push(join(base, 'Google', 'Chrome', 'Application', 'chrome.exe'), join(base, 'Microsoft', 'Edge', 'Application', 'msedge.exe'))
    }
  } else if (process.platform === 'darwin') {
    candidates.push(
      '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome',
      '/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge',
      '/Applications/Chromium.app/Contents/MacOS/Chromium',
    )
  } else {
    candidates.push(...onPath(['google-chrome', 'google-chrome-stable', 'chromium', 'chromium-browser', 'microsoft-edge']))
  }
  candidates.push(...playwrightChromium())
  return candidates.find((path) => existsSync(path)) ?? null
}

function runBrowser(binary: string, args: string[], timeoutMs: number): Promise<void> {
  return new Promise((resolve, reject) => {
    const child = spawn(binary, args, { stdio: 'ignore', windowsHide: true })
    const timer = setTimeout(() => {
      child.kill()
      reject(new ExportError('render_failed', `the browser did not finish printing in ${timeoutMs / 1000} s`))
    }, timeoutMs)
    child.once('error', (error) => {
      clearTimeout(timer)
      reject(new ExportError('render_failed', `the browser could not start: ${error.message}`))
    })
    child.once('exit', () => {
      clearTimeout(timer)
      resolve()
    })
  })
}

export async function exportPdf(doc: PMNode, options: ExportOptions, chromium: string | null): Promise<Buffer> {
  if (!chromium) throw new ExportError('pdf_unavailable', 'PDF export needs Chrome, Edge or Chromium on the host')
  const dir = mkdtempSync(join(tmpdir(), 'bb-pdf-'))
  try {
    const page = join(dir, 'document.html')
    const out = join(dir, 'document.pdf')
    writeFileSync(page, printHtml(doc, options))
    const args = [
      '--headless=new',
      '--disable-gpu',
      '--no-first-run',
      '--no-default-browser-check',
      '--disable-extensions',
      // No --blink-settings=scriptEnabled=false: Chrome then prints nothing. The page's
      // Content-Security-Policy blocks scripts instead.
      `--user-data-dir=${join(dir, 'profile')}`,
      '--no-pdf-header-footer',
      '--print-to-pdf-no-header',
      `--print-to-pdf=${out}`,
    ]
    if (process.platform === 'linux' && process.getuid?.() === 0) args.push('--no-sandbox')
    await runBrowser(chromium, [...args, pathToFileURL(page).href], 60000)
    if (!existsSync(out)) throw new ExportError('render_failed', 'the browser wrote no PDF')
    return readFileSync(out)
  } finally {
    rmSync(dir, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 })
  }
}
