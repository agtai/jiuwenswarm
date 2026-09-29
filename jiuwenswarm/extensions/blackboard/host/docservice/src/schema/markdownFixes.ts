// Markdown serializer fixes and tokenizer guards found in spike 1 (notes/blackboard/spikes/RESULTS.md).
import { Extension } from '@tiptap/core'

// Text at the start of a line that Markdown would read as block syntax gets a backslash.
export function escapeLineStarts(text: string): string {
  return text
    .split('\n')
    .map((line) => {
      let m: RegExpExecArray | null
      if ((m = /^( {0,3})(#{1,6})(?=[ \t]|$)/.exec(line))) return m[1] + '\\' + line.slice(m[1].length)
      if ((m = /^( {0,3})([-+])(?=[ \t]|$)/.exec(line))) return m[1] + '\\' + line.slice(m[1].length)
      if ((m = /^( {0,3})(\d{1,9})([.)])(?=[ \t]|$)/.exec(line))) return m[1] + m[2] + '\\' + line.slice(m[1].length + m[2].length)
      if ((m = /^( {0,3})(=+|-+)[ \t]*$/.exec(line))) return m[1] + '\\' + line.slice(m[1].length)
      if ((m = /^( {0,3})((?:-[ \t]*){3,})$/.exec(line))) return m[1] + '\\' + line.slice(m[1].length)
      return line
    })
    .join('\n')
}

// Tiptap's ordered-list, task-list and table tokenizers split the whole remaining document into
// lines at every block position, which makes parsing quadratic (127 KB took 4.8 s). These guards
// return early unless the text at the position can start the construct.
export function guarded(tokenizer: any, re: RegExp): any {
  return { ...tokenizer, tokenize: (src: string, tokens: unknown, lexer: unknown) => (re.test(src) ? tokenizer.tokenize(src, tokens, lexer) : undefined) }
}

export function tableStart(src: string): number {
  const i1 = src.indexOf('\n')
  if (i1 < 0) return -1
  const i2 = src.indexOf('\n', i1 + 1)
  const sep = src.slice(i1 + 1, i2 < 0 ? src.length : i2)
  if (!/^[ \t|:]*-[ \t|:-]*$/.test(sep) || !sep.includes('|')) return -1
  return src.slice(0, i1).includes('|') ? 0 : -1
}

// Placeholders while a table is serialized: cells escape every pipe (GFM requires it inside code
// spans too) and keep hard breaks as <br>.
export const PIPE = String.fromCharCode(0xe000)
export const BREAK = String.fromCharCode(0xe001)

// `<br>` becomes a hard break. On the server the Markdown parser has no DOMParser, so other HTML
// stays literal text; <br> is the one tag the table serializer itself emits.
export const HtmlBreak = Extension.create({
  name: 'bbHtmlBreak',
  markdownTokenizer: {
    name: 'bbHtmlBreak',
    level: 'inline',
    start: (src: string) => src.search(/<br\s*\/?>/i),
    tokenize: (src: string) => {
      const m = /^<br\s*\/?>/i.exec(src)
      return m ? { type: 'br', raw: m[0] } : undefined
    },
  },
} as any)
