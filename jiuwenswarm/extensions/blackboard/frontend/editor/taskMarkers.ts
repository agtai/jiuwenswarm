// Where jiuwen works on a task given from this document (Ctrl+J): three moving dots at the end of
// the text where the cursor was, until the run ends. The place is found by block id, so the dots
// follow the text while people and agents edit.
import { Extension, type Editor } from '@tiptap/core';
import type { Node as PMNode } from '@tiptap/pm/model';
import { Plugin, PluginKey } from '@tiptap/pm/state';
import { Decoration, DecorationSet } from '@tiptap/pm/view';

import type { WorkingPlace } from '../types';

interface MarkerState {
  places: WorkingPlace[];
  decorations: DecorationSet;
}

export interface TaskMarkersOptions {
  // The dots' accessible name, such as "jiuwen is working".
  label: () => string;
}

const markersKey = new PluginKey<MarkerState>('bbTaskMarkers');

// For each place, the end of the last text in its last block (after the block when it has no text).
export function dotPositions(doc: PMNode, places: WorkingPlace[]): number[] {
  const out: number[] = [];
  for (const place of places) {
    doc.forEach((node, offset) => {
      if (node.attrs.id !== place.to) return;
      if (node.isTextblock) {
        out.push(offset + node.nodeSize - 1);
        return;
      }
      let end = offset + node.nodeSize;
      node.descendants((child, pos) => {
        if (child.isTextblock) end = offset + 1 + pos + child.nodeSize - 1;
      });
      out.push(end);
    });
  }
  return out;
}

function dots(label: string): HTMLElement {
  const el = document.createElement('span');
  el.className = 'bb-task-dots';
  el.contentEditable = 'false';
  el.setAttribute('role', 'status');
  el.setAttribute('aria-label', label);
  el.title = label;
  el.dataset.testid = 'blackboard-task-working';
  for (let i = 0; i < 3; i += 1) el.append(document.createElement('i'));
  return el;
}

export const TaskMarkers = Extension.create<TaskMarkersOptions>({
  name: 'bbTaskMarkers',

  addOptions() {
    return { label: () => '' };
  },

  addProseMirrorPlugins() {
    const { label } = this.options;
    const decorate = (doc: PMNode, places: WorkingPlace[]) =>
      places.length
        ? DecorationSet.create(
            doc,
            dotPositions(doc, places).map((pos) => Decoration.widget(pos, () => dots(label()), { side: 1, key: `bb-task-${pos}`, ignoreSelection: true })),
          )
        : DecorationSet.empty;
    return [
      new Plugin<MarkerState>({
        key: markersKey,
        state: {
          init: () => ({ places: [], decorations: DecorationSet.empty }),
          apply(tr, previous, _old, next) {
            const places = (tr.getMeta(markersKey) as WorkingPlace[] | undefined) ?? previous.places;
            if (places === previous.places && !tr.docChanged) return previous;
            return { places, decorations: decorate(next.doc, places) };
          },
        },
        props: { decorations: (state) => markersKey.getState(state)?.decorations },
      }),
    ];
  },
});

export function showTaskMarkers(editor: Editor, places: WorkingPlace[]): void {
  const current = markersKey.getState(editor.state)?.places ?? [];
  if (JSON.stringify(current) === JSON.stringify(places)) return;
  editor.view.dispatch(editor.state.tr.setMeta(markersKey, places));
}
