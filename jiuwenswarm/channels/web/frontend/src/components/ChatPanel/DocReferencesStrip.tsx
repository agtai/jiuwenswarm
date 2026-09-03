/**
 * Session references: chips for the cloud documents this conversation touched,
 * each jumping to that document's receipts in the Docs panel. The source of
 * truth is the session's own tool executions -- a document appears here because
 * a clouddoc tool actually named it, not because the model mentioned it.
 */
import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useChatStore } from '../../stores/chatStore';
import { webRequest } from '../../services/webClient';
import { requestOpenDoc } from '../../features/clouddoc/openDocSignal';

export function DocReferencesStrip() {
  const { t } = useTranslation();
  const activeSessionId = useChatStore((s) => s.activeSessionId);
  const toolExecutions = useChatStore(
    (s) => s.runtimes[activeSessionId ?? '']?.toolExecutions,
  );

  const docIds = useMemo(() => {
    const ids: string[] = [];
    if (toolExecutions) {
      for (const exec of toolExecutions.values()) {
        const name = exec.toolCall?.name ?? '';
        if (!name.startsWith('clouddoc_')) continue;
        const docId = exec.toolCall?.arguments?.doc_id;
        if (typeof docId === 'string' && docId && !ids.includes(docId)) {
          ids.push(docId);
        }
      }
    }
    return ids;
  }, [toolExecutions]);

  // Titles come from the deployment's own document list; a doc outside it
  // (possible on widened grants) falls back to its id, still clickable.
  const [titles, setTitles] = useState<Record<string, string>>({});
  useEffect(() => {
    if (docIds.length === 0) return;
    let alive = true;
    webRequest<{ docs?: { doc_id: string; title?: string }[] }>('clouddoc.list_docs')
      .then((out) => {
        if (!alive) return;
        const map: Record<string, string> = {};
        for (const d of out?.docs ?? []) {
          if (d.doc_id && d.title) map[d.doc_id] = d.title;
        }
        setTitles(map);
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [docIds.length]);

  if (docIds.length === 0) return null;

  return (
    <div className="doc-refs-strip" data-testid="doc-references-strip">
      <span className="doc-refs-strip__label">{t('chat.docRefs.label')}</span>
      {docIds.map((id) => (
        <button
          key={id}
          type="button"
          className="doc-refs-strip__chip"
          title={t('chat.docRefs.hint')}
          onClick={() => requestOpenDoc(id)}
          data-testid={`doc-ref-chip-${id}`}
        >
          <span aria-hidden="true">📄</span>
          <span className="doc-refs-strip__chip-title">
            {titles[id] ?? `${id.slice(0, 10)}…`}
          </span>
        </button>
      ))}
    </div>
  );
}
