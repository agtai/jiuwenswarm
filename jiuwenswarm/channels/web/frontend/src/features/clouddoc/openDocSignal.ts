/**
 * The handoff between a chat reference chip (or a Docs panel row) and the
 * document workbench (release §14). A click can race a view's mount -- the nav
 * switch and the event fire in the same tick -- so the doc id travels through
 * this module-level latch rather than the event payload: the event only says
 * "look", and the one consumer (App, which owns the workbench) gets the id
 * exactly once.
 */

export const OPEN_DOC_EVENT = 'jiuwen:clouddoc-open-doc';

let pendingDocId: string | null = null;
// A receipt the opener wants landed on, travelling with the id for the same
// reason the id does: the workbench may not be mounted yet, and an event
// payload read by nobody is a locate that silently does nothing.
let pendingReceiptId = '';

export function requestOpenDoc(docId: string, receiptId = ''): void {
  pendingDocId = docId;
  pendingReceiptId = receiptId;
  window.dispatchEvent(new Event(OPEN_DOC_EVENT));
}

export function consumePendingOpenDoc(): { docId: string; receiptId: string } | null {
  const v = pendingDocId;
  const r = pendingReceiptId;
  pendingDocId = null;
  pendingReceiptId = '';
  return v ? { docId: v, receiptId: r } : null;
}
