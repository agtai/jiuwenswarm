// Comment threads in the editor: their passages highlighted, a click opening the thread, and the
// anchor a new comment is made on. Anchors are Yjs relative positions, so a passage follows other
// people's edits; like y-tiptap's cursor plugin, the highlights are computed again from those
// positions when remote changes arrive or the threads change, and mapped through local edits.
import { Extension, type Editor } from '@tiptap/core';
import type { Node as PMNode } from '@tiptap/pm/model';
import { Plugin, PluginKey, type EditorState } from '@tiptap/pm/state';
import { Decoration, DecorationSet } from '@tiptap/pm/view';
import { absolutePositionToRelativePosition, relativePositionToAbsolutePosition, ySyncPluginKey } from '@tiptap/y-tiptap';
import * as Y from 'yjs';

import { fromBase64, normalizeText, toBase64 } from '../conversation';
import type { AnchorDraft, AnchorStatus } from '../types';

// The block separator of quotes; the document service compares with the same one.
const SEPARATOR = '\n';
// The host's bound on a selection; the Comment button says so above it.
const MAX_QUOTE = 100_000;

export interface ThreadAnchor {
  id: string;
  start: string;
  end: string;
  quote: string;
  status: AnchorStatus;
}

interface CommentState {
  anchors: ThreadAnchor[];
  active: string | null;
  decorations: DecorationSet;
}

type CommentMeta = { anchors: ThreadAnchor[]; active: string | null };

export const commentsKey = new PluginKey<CommentState>('bbComments');

// The accepted text of a range, as the document service reads it: text a pending suggestion inserts
// is left out, and text blocks are separated like ProseMirror's textBetween.
export function acceptedText(doc: PMNode, from: number, to: number): string {
  let text = '';
  let first = true;
  doc.nodesBetween(from, to, (node, pos) => {
    if (node.isBlock && node.isTextblock) {
      if (first) first = false;
      else text += SEPARATOR;
    }
    if (node.isText && !node.marks.some((m) => m.type.name === 'insertion')) {
      text += node.text!.slice(Math.max(from, pos) - pos, to - pos);
    }
  });
  return text;
}

function decode(position: string): Y.RelativePosition | null {
  try {
    return Y.decodeRelativePosition(fromBase64(position));
  } catch {
    return null;
  }
}

// Where each thread's passage is now, and whether its text still matches the quote.
export function locate(state: EditorState, anchors: ThreadAnchor[]): Array<{ id: string; from: number; to: number; drifted: boolean }> {
  const ystate = ySyncPluginKey.getState(state);
  if (!ystate?.binding || !ystate.doc || ystate.binding.mapping.size === 0) return [];
  const out = [];
  for (const anchor of anchors) {
    if (anchor.status === 'orphaned') continue;
    const start = decode(anchor.start);
    const end = decode(anchor.end);
    const from = start ? relativePositionToAbsolutePosition(ystate.doc, ystate.type, start, ystate.binding.mapping) : null;
    const to = end ? relativePositionToAbsolutePosition(ystate.doc, ystate.type, end, ystate.binding.mapping) : null;
    if (from === null || to === null || from >= to || to > state.doc.content.size) continue;
    const now = acceptedText(state.doc, from, to);
    out.push({ id: anchor.id, from, to, drifted: normalizeText(now) !== normalizeText(anchor.quote) });
  }
  return out;
}

function decorate(state: EditorState, anchors: ThreadAnchor[], active: string | null): DecorationSet {
  const decorations = locate(state, anchors).map(({ id, from, to, drifted }) =>
    Decoration.inline(from, to, {
      class: `bb-comment${drifted ? ' is-drifted' : ''}${id === active ? ' is-active' : ''}`,
      'data-thread': id,
    }),
  );
  return DecorationSet.create(state.doc, decorations);
}

export interface CommentHighlightsOptions {
  // A click on a highlighted passage, or null for a click on other text.
  onOpenThread: (threadId: string | null) => void;
  // Ctrl+M on a selection; false when the person cannot comment.
  onComment: (anchor: AnchorDraft) => boolean;
}

export const CommentHighlights = Extension.create<CommentHighlightsOptions>({
  name: 'bbCommentHighlights',

  addOptions() {
    return { onOpenThread: () => undefined, onComment: () => false };
  },

  addKeyboardShortcuts() {
    return {
      'Ctrl-m': () => {
        const anchor = anchorForSelection(this.editor.state);
        return anchor ? this.options.onComment(anchor) : false;
      },
    };
  },

  addProseMirrorPlugins() {
    const options = this.options;
    return [
      new Plugin<CommentState>({
        key: commentsKey,
        state: {
          init: (_, state) => ({ anchors: [], active: null, decorations: DecorationSet.create(state.doc, []) }),
          apply(tr, previous, _old, next) {
            const meta = tr.getMeta(commentsKey) as CommentMeta | undefined;
            const remote = Boolean(ySyncPluginKey.getState(next)?.isChangeOrigin);
            const anchors = meta?.anchors ?? previous.anchors;
            const active = meta ? meta.active : previous.active;
            if (meta || remote) return { anchors, active, decorations: decorate(next, anchors, active) };
            if (tr.docChanged) return { anchors, active, decorations: previous.decorations.map(tr.mapping, tr.doc) };
            return previous;
          },
        },
        props: {
          decorations: (state) => commentsKey.getState(state)?.decorations,
          handleClick: (_view, _pos, event) => {
            const target = (event.target as HTMLElement | null)?.closest?.('[data-thread]') as HTMLElement | null;
            options.onOpenThread(target?.dataset.thread ?? null);
            return false;
          },
        },
      }),
    ];
  },
});

export function showThreads(editor: Editor, anchors: ThreadAnchor[], active: string | null): void {
  editor.view.dispatch(editor.state.tr.setMeta(commentsKey, { anchors, active }).setMeta('addToHistory', false));
}

// The selection as the anchor of a new comment, or null when nothing (or nothing textual) is selected.
export function anchorForSelection(state: EditorState): AnchorDraft | null {
  const { from, to, empty } = state.selection;
  if (empty) return null;
  const ystate = ySyncPluginKey.getState(state);
  if (!ystate?.binding || !ystate.type) return null;
  const quote = acceptedText(state.doc, from, to);
  if (!quote.trim() || quote.length > MAX_QUOTE) return null;
  const $from = state.doc.resolve(from);
  const $to = state.doc.resolve(to);
  if ($from.depth < 1 || $to.depth < 1) return null;
  const first = $from.node(1);
  const blockStart = $from.before(1);
  const encode = (pos: number) => toBase64(Y.encodeRelativePosition(absolutePositionToRelativePosition(pos, ystate.type, ystate.binding.mapping)));
  return {
    block_id: String(first.attrs.id ?? ''),
    block_to: String($to.node(1).attrs.id ?? first.attrs.id ?? ''),
    digest: null,
    start: encode(from),
    end: encode(to),
    quote,
    offset: acceptedText(state.doc, blockStart, from).length,
    length: quote.length,
  };
}

export function selectionTooLong(state: EditorState): boolean {
  const { from, to, empty } = state.selection;
  return !empty && acceptedText(state.doc, from, to).length > MAX_QUOTE;
}

// A passage's place, to scroll the editor to a thread.
export function threadRange(state: EditorState, anchor: ThreadAnchor): { from: number; to: number } | null {
  return locate(state, [anchor])[0] ?? null;
}

export { MAX_QUOTE };
