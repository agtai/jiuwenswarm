// Everything a person types or pastes carries their author mark. The document service rejects
// updates that add text credited to someone else, so pasted text loses other people's author and
// suggestion marks here, before it is sent.
import { Extension } from '@tiptap/core';
import type { Mark, MarkType, Node as PMNode } from '@tiptap/pm/model';
import { Plugin, PluginKey, type EditorState, type Transaction } from '@tiptap/pm/state';
import { relativePositionToAbsolutePosition, ySyncPluginKey } from '@tiptap/y-tiptap';
import * as Y from 'yjs';

export interface Author {
  id: string;
  kind: 'person';
}

type Range = [number, number];

const SUGGESTIONS = ['insertion', 'deletion', 'modification'];
export const authorStampKey = new PluginKey('bbAuthorStamp');

function isRemote(tr: Transaction): boolean {
  // y-tiptap marks the transactions that apply Yjs changes to the editor.
  return Boolean(tr.getMeta('y-sync$')) || Boolean(tr.getMeta(authorStampKey));
}

// Ranges in the final document that local transactions inserted or replaced.
export function insertedRanges(transactions: readonly Transaction[]): Range[] {
  let ranges: Range[] = [];
  for (const tr of transactions) {
    const mapped: Range[] = [];
    for (const [from, to] of ranges) {
      const start = tr.mapping.map(from, 1);
      const end = tr.mapping.map(to, -1);
      if (end > start) mapped.push([start, end]);
    }
    ranges = mapped;
    if (!tr.docChanged || isRemote(tr)) continue;
    tr.mapping.maps.forEach((map, index) => {
      const rest = tr.mapping.slice(index + 1);
      map.forEach((_oldStart, _oldEnd, newStart, newEnd) => {
        const start = rest.map(newStart, 1);
        const end = rest.map(newEnd, -1);
        if (end > start) ranges.push([start, end]);
      });
    });
  }
  return ranges;
}

function foreignSuggestion(mark: Mark, me: Author): boolean {
  return SUGGESTIONS.includes(mark.type.name) && mark.attrs.author?.id !== me.id;
}

export function stampAuthor(state: EditorState, ranges: Range[], me: Author): Transaction | null {
  const authorType: MarkType | undefined = state.schema.marks.author;
  if (!authorType || ranges.length === 0) return null;
  const mark = authorType.create({ id: me.id, kind: me.kind });
  const tr = state.tr;
  for (const [from, to] of ranges) {
    state.doc.nodesBetween(from, to, (node: PMNode, pos: number) => {
      for (const m of node.marks) {
        if (!foreignSuggestion(m, me)) continue;
        if (node.isText) tr.removeMark(Math.max(from, pos), Math.min(to, pos + node.nodeSize), m);
        else tr.removeNodeMark(pos, m);
      }
      if (node.isText && !mark.isInSet(node.marks)) {
        tr.addMark(Math.max(from, pos), Math.min(to, pos + node.nodeSize), mark);
      }
      return true;
    });
  }
  if (!tr.docChanged) return null;
  // No addToHistory: false here. y-tiptap takes that flag from the last transaction of a
  // dispatch, so it would keep the typing itself out of undo.
  return tr.setMeta(authorStampKey, true);
}

// The text an undo or redo brought back: new items of this client in that Yjs transaction.
function restoredText(tr: Y.Transaction): Array<[Y.RelativePosition, Y.RelativePosition]> {
  const client = tr.doc.clientID;
  const since = tr.beforeState.get(client) ?? 0;
  const structs = tr.doc.store.clients.get(client) ?? [];
  const byText = new Map<Y.XmlText, Set<Y.Item>>();
  for (let i = structs.length - 1; i >= 0 && structs[i].id.clock + structs[i].length > since; i -= 1) {
    const item = structs[i];
    if (!(item instanceof Y.Item) || item.deleted || !(item.content instanceof Y.ContentString)) continue;
    if (!(item.parent instanceof Y.XmlText)) continue;
    const items = byText.get(item.parent) ?? new Set<Y.Item>();
    items.add(item);
    byText.set(item.parent, items);
  }
  const runs: Array<[Y.RelativePosition, Y.RelativePosition]> = [];
  for (const [text, items] of byText) {
    let index = 0;
    for (let item = text._start; item !== null; item = item.right) {
      if (items.has(item)) {
        runs.push([Y.createRelativePositionFromTypeIndex(text, index), Y.createRelativePositionFromTypeIndex(text, index + item.length)]);
      }
      if (!item.deleted && item.countable) index += item.length;
    }
  }
  return runs;
}

export const AuthorStamp = Extension.create<{ getAuthor: () => Author | null; document: Y.Doc | null }>({
  name: 'bbAuthorStamp',
  addOptions() {
    return { getAuthor: () => null, document: null };
  },
  addProseMirrorPlugins() {
    const getAuthor = () => this.options.getAuthor();
    const ydoc = this.options.document;
    return [
      new Plugin({
        key: authorStampKey,
        appendTransaction(transactions, _old, state) {
          const me = getAuthor();
          if (!me) return null;
          return stampAuthor(state, insertedRanges(transactions), me);
        },
        // Undo and redo bring text back through Yjs (someone else's, say); it is credited to the
        // person who undid. The binding ignores editor changes made while it applies a Yjs change,
        // so the stamp follows just after, and the provider's batching sends both as one update.
        view(view) {
          if (!ydoc) return {};
          let pending: Array<[Y.RelativePosition, Y.RelativePosition]> = [];
          let timer: ReturnType<typeof setTimeout> | null = null;
          const flush = () => {
            timer = null;
            const runs = pending;
            pending = [];
            const me = getAuthor();
            const sync = ySyncPluginKey.getState(view.state);
            if (!me || !sync?.binding) return;
            const ranges: Range[] = [];
            for (const [start, end] of runs) {
              const from = relativePositionToAbsolutePosition(ydoc, sync.type, start, sync.binding.mapping);
              const to = relativePositionToAbsolutePosition(ydoc, sync.type, end, sync.binding.mapping);
              if (from !== null && to !== null && to > from) ranges.push([from, to]);
            }
            const tr = stampAuthor(view.state, ranges, me);
            // Kept out of undo, so it neither becomes an undo step nor clears redo.
            if (tr) view.dispatch(tr.setMeta('addToHistory', false));
          };
          const afterTransaction = (tr: Y.Transaction) => {
            if (!(tr.origin instanceof Y.UndoManager)) return;
            pending.push(...restoredText(tr));
            if (pending.length > 0 && timer === null) timer = setTimeout(flush, 0);
          };
          ydoc.on('afterTransaction', afterTransaction);
          return {
            destroy() {
              ydoc.off('afterTransaction', afterTransaction);
              if (timer !== null) clearTimeout(timer);
            },
          };
        },
      }),
    ];
  },
});
