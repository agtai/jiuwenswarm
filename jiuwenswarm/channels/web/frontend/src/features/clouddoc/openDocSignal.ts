/**
 * The handoff between a chat reference chip (or a Docs panel row) and the
 * document workbench (release §14). A click can race a view's mount -- the nav
 * switch and the event fire in the same tick -- so the doc id travels through
 * this module-level latch rather than the event payload: the event only says
 * "look", and the one consumer (App, which owns the workbench) gets the id
 * exactly once.
 */

export const OPEN_DOC_EVENT = 'jiuwen:clouddoc-open-doc';

/** What travels with an open request: a composer prefill (a notice's "handle it"). */
export interface OpenDocContext {
  prompt?: string;
}

let pendingDocId: string | null = null;
let pendingContext: OpenDocContext | null = null;

export function requestOpenDoc(docId: string, context?: OpenDocContext): void {
  pendingDocId = docId;
  pendingContext = context ?? null;
  window.dispatchEvent(new Event(OPEN_DOC_EVENT));
}

export function consumePendingOpenDoc(): string | null {
  const v = pendingDocId;
  pendingDocId = null;
  return v;
}

export function consumePendingOpenContext(): OpenDocContext | null {
  const v = pendingContext;
  pendingContext = null;
  return v;
}
