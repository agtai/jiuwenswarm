/**
 * The registered documents, for the composer's ``@`` picker.
 *
 * The backend marks a document ``user_named`` when the session's user text
 * contains its title or id, and tells the model to stay on that one. Typing the
 * title by hand is the only way to say it today; the picker inserts the exact
 * title, so the same match fires without the person remembering the name.
 *
 * One fetch shared by every composer on the page, refreshed when the ledger
 * moves (a registration is a ledger event too) and never before the first
 * request, so a page without the plugin costs nothing.
 */
import { useEffect, useState } from 'react';
import { webClient, webRequest } from '../../../../../channels/web/frontend/src/services/webClient';

export type RegisteredDoc = { docId: string; title: string; kind: string };

type DocRow = { doc_id: string; title?: string; kind?: string };

let cache: RegisteredDoc[] = [];
let inflight: Promise<RegisteredDoc[]> | null = null;
const listeners = new Set<(docs: RegisteredDoc[]) => void>();

function fetchDocs(): Promise<RegisteredDoc[]> {
  if (inflight) return inflight;
  inflight = webRequest<{ docs?: DocRow[] }>('clouddoc.list_docs')
    .then((out) => (out?.docs ?? [])
      .filter((d) => d.doc_id && d.title)
      .map((d) => ({ docId: d.doc_id, title: d.title || d.doc_id, kind: d.kind || 'document' })))
    .catch(() => cache)
    .then((docs) => {
      cache = docs;
      inflight = null;
      listeners.forEach((fn) => fn(docs));
      return docs;
    });
  return inflight;
}

export function useRegisteredDocs(): RegisteredDoc[] {
  const [docs, setDocs] = useState<RegisteredDoc[]>(cache);
  useEffect(() => {
    listeners.add(setDocs);
    void fetchDocs();
    const off = webClient.on('clouddoc.receipts_changed', () => { void fetchDocs(); });
    return () => { listeners.delete(setDocs); off(); };
  }, []);
  return docs;
}
