/**
 * The right rail: receipts and status follow the focused document; chat
 * history is the whole session across documents. (A threads tab waits on a
 * panel API for comment threads; see the release notes' backlog.)
 */
import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { PanelRightClose } from 'lucide-react';
import { webRequest } from '../../services/webClient';
import { useChatStore } from '../../stores/chatStore';
import { useSessionStore } from '../../stores/sessionStore';
import { ChatTimelineList } from '../ChatPanel/MessageList';
import { KindIcon } from './KindIcon';
import { RECEIPT_OP_KEY, RECEIPT_STATUS_KEY, receiptRegions, type ReceiptRow } from '../../features/clouddoc/receipts';
import type { RailTab, WorkbenchTab } from '../../stores/docWorkbenchStore';

const TONE: Record<string, string> = {
  applied: 'ok', applied_unverified: 'warn', pending: 'warn', aborted: 'muted', reverted: 'muted', unknown: 'warn',
};

export type WatchInfo = { mode: string; suspended: boolean; expires_at?: number | null; expired?: boolean } | undefined;

export function SideRail({
  tab, tabs, railTab, receipts, watch, globalSuspended, onTab, onRefresh, onLocate, onJump, onWatch, onHide,
}: {
  tab: WorkbenchTab | null;
  tabs: WorkbenchTab[];
  railTab: RailTab;
  receipts: ReceiptRow[];
  watch: WatchInfo;
  globalSuspended: boolean;
  onTab: (t: RailTab) => void;
  onRefresh: () => void;
  onLocate: (r: ReceiptRow) => void;
  onJump: (docId: string) => void;
  onWatch: (mode: 'off' | 'reply_only' | 'apply_scoped' | 'suspend' | 'resume') => void;
  onHide: () => void;
}) {
  const { t } = useTranslation();
  const sid = useChatStore((s) => s.activeSessionId) ?? '';
  const messages = useChatStore((s) => s.runtimes[sid]?.messages ?? []);
  const executions = useChatStore((s) => s.runtimes[sid]?.toolExecutions);
  const mode = useSessionStore((s) => s.runtimes[sid]?.mode ?? 'agent');
  const [acting, setActing] = useState<string | null>(null);
  // The one revert that asks: a receipt whose read-back disagreed (applied_unverified)
  // arms on the first click and runs on the second. Everything else is reversible
  // and reverts straight away, leaving its own receipt.
  const [armedRevert, setArmedRevert] = useState<string | null>(null);
  const [note, setNote] = useState<string | null>(null);

  const act = useCallback(async (method: 'clouddoc.revert' | 'clouddoc.unhighlight', receiptId: string) => {
    setActing(receiptId);
    setNote(null);
    try {
      const out = await webRequest<{ ok?: boolean; detail?: string }>(method, { receipt_id: receiptId }, { timeoutMs: 60_000 });
      if (out && out.ok === false) setNote(out.detail || t('docs.history.failed'));
    } catch {
      setNote(t('docs.history.actionUnconfirmed'));
    } finally {
      setActing(null);
      onRefresh();
    }
  }, [onRefresh, t]);

  useEffect(() => { setNote(null); setArmedRevert(null); }, [tab?.docId]);

  const elsewhere = tabs.filter((x) => x.docId !== tab?.docId && x.unread > 0);
  const tierLabel = !watch ? t('docs.watch.watchOff')
    : watch.expired ? t('docs.watch.watchExpired')
      : watch.suspended || globalSuspended ? t('docs.watch.watchSuspended')
        : watch.mode === 'apply_scoped' ? t('docs.watch.watchApply') : t('docs.watch.watchReply');

  return (
    <aside className="doc-workbench__rail" data-testid="doc-workbench-rail">
      <div className="doc-workbench__rail-tabs" role="tablist">
        {(['receipts', 'history', 'status'] as RailTab[]).map((k) => (
          <button key={k} type="button" role="tab" aria-selected={railTab === k} className={`doc-workbench__rail-tab${railTab === k ? ' doc-workbench__rail-tab--active' : ''}`} onClick={() => onTab(k)} data-testid="doc-workbench-rail-tab" data-variant={k}>
            {t(`docs.workbench.rail.${k}`)}
            {k === 'receipts' && receipts.length > 0 && <span className="rounded-full bg-bg-muted px-1.5 text-[10px] text-text-muted">{receipts.length}</span>}
          </button>
        ))}
        <span className="ml-auto" />
        <button type="button" className="doc-workbench__icon-btn" style={{ width: 26, height: 26 }} onClick={onHide} title={t('docs.workbench.toggleRail')} data-testid="doc-workbench-rail-hide">
          <PanelRightClose size={15} />
        </button>
      </div>

      {railTab === 'receipts' && (
        <div className="doc-workbench__rail-body" data-testid="doc-workbench-receipts">
          <div className="flex items-center gap-2 px-0.5 pb-1 text-[11px] text-text-muted">
            <span className="min-w-0 truncate">{t('docs.workbench.thisTab')} · {tab?.title || tab?.docId}</span>
          </div>
          {elsewhere.length > 0 && (
            <div className="doc-workbench__elsewhere" data-testid="doc-workbench-elsewhere">
              <span className="doc-workbench__tab-dot" style={{ background: 'var(--color-conversation-unread)' }} />
              <span className="flex-1">{t('docs.workbench.elsewhere', { n: elsewhere.reduce((a, x) => a + x.unread, 0) })}</span>
              {elsewhere.map((x) => (
                <a key={x.docId} className="inline-flex items-center gap-1 text-[11px] hover:underline" onClick={() => onJump(x.docId)}>
                  <KindIcon kind={x.kind} provider={x.provider} size={12} /> {x.title || x.docId} ·{x.unread}
                </a>
              ))}
            </div>
          )}
          {note && <p className="text-xs text-red-600" data-testid="doc-workbench-receipt-note">{note}</p>}
          {receipts.length === 0 && <p className="py-6 text-center text-xs text-text-muted">{t('docs.history.empty')}</p>}
          {receipts.map((r) => {
            const regions = receiptRegions(r);
            const isLifecycle = r.op && r.op !== 'edit';
            return (
              <div key={r.receipt_id} className="doc-workbench__receipt" data-testid="doc-workbench-receipt" data-variant={r.status}>
                <div className="doc-workbench__receipt-head">
                  <span className="font-mono text-[11px] text-text-muted">{r.receipt_id.slice(0, 8)}</span>
                  <span className={`doc-workbench__chip doc-workbench__chip--${TONE[r.status] ?? 'muted'}`}>{t(RECEIPT_STATUS_KEY[r.status] ?? '', { defaultValue: r.status })}</span>
                  <span className="flex-1" />
                  <span className="text-[11px] text-text-muted">{new Date((r.ts || 0) * 1000).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                </div>
                {isLifecycle ? (
                  <span className="text-xs text-text">
                    <span className="font-medium">{t(RECEIPT_OP_KEY[r.op as string] ?? '', { defaultValue: r.op })}</span>
                    {r.subject?.email ? ` · ${r.subject.email}` : ''}{r.subject?.title ? ` · ${r.subject.title}` : ''}
                  </span>
                ) : (
                  <span className="truncate text-xs text-text">
                    {regions.length > 0 ? regions.join(', ') : (r.edits?.[0]?.new || r.edits?.[0]?.old || '')}
                    {(r.edits?.length ?? 0) > 1 ? ` · ${t('docs.history.more', { n: (r.edits?.length ?? 1) - 1 })}` : ''}
                  </span>
                )}
                {r.unverified_detail && <span className="text-[11px] text-amber-700">{r.unverified_detail}</span>}
                {r.superseded_by && (
                  <span className="text-[11px] text-text-muted" data-testid="doc-workbench-receipt-superseded">
                    {t('docs.history.superseded', { id: r.superseded_by.slice(0, 8) })}
                  </span>
                )}
                {r.status === 'reverted' && r.reverted_by && <span className="text-[11px] text-text-muted">{t('docs.history.revertedBy', { id: r.reverted_by.slice(0, 8) })}</span>}
                <div className="flex items-center gap-3">
                  {!isLifecycle && (r.status === 'applied' || r.status === 'applied_unverified') && (
                    <a className="text-xs text-text-link hover:underline" onClick={() => onLocate(r)} data-testid="doc-workbench-receipt-locate">{t('docs.workbench.locate')}</a>
                  )}
                  {(r.status === 'applied' || r.status === 'applied_unverified') && !r.superseded_by && (
                    <button
                      type="button"
                      className="text-xs text-text-link hover:underline disabled:opacity-50"
                      disabled={acting === r.receipt_id}
                      data-testid="doc-workbench-receipt-revert"
                      data-armed={armedRevert === r.receipt_id || undefined}
                      onClick={() => {
                        if (r.status === 'applied_unverified' && armedRevert !== r.receipt_id) {
                          setArmedRevert(r.receipt_id);
                          return;
                        }
                        setArmedRevert(null);
                        void act('clouddoc.revert', r.receipt_id);
                      }}
                    >
                      {armedRevert === r.receipt_id ? t('docs.history.revertConfirm') : t('docs.workbench.revert')}
                    </button>
                  )}
                  {r.status === 'applied' && r.highlight && (
                    <button type="button" className="text-xs text-text-link hover:underline disabled:opacity-50" disabled={acting === r.receipt_id} onClick={() => void act('clouddoc.unhighlight', r.receipt_id)}>{t('docs.history.unhighlight')}</button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {railTab === 'history' && (
        <div className="doc-workbench__rail-body" data-testid="doc-workbench-history">
          <div className="px-0.5 pb-1 text-[11px] text-text-muted">{t('docs.workbench.historyNote')}</div>
          <ChatTimelineList messages={messages} executions={executions ? Array.from(executions.values()) : []} mode={mode} disableA2UIInteraction />
        </div>
      )}

      {railTab === 'status' && tab && (
        <div className="doc-workbench__rail-body" data-testid="doc-workbench-status">
          <div className="doc-workbench__receipt">
            <span className="text-xs font-medium">{tierLabel}</span>
            {watch?.expires_at && !watch.expired && <span className="text-[11px] text-text-muted">{t('docs.usage.until')} {new Date(watch.expires_at * 1000).toLocaleString()}</span>}
            <span className="text-[11px] text-text-muted">{tab.providerName || tab.provider} · {t(`docs.kind.${tab.kind}`, { defaultValue: tab.kind })}</span>
          </div>
        </div>
      )}

      {tab && (
        <div className="doc-workbench__rail-foot" data-testid="doc-workbench-rail-foot">
          <div className="flex items-center gap-2">
            <span className="doc-workbench__dot" style={{ background: watch && !watch.expired && !watch.suspended && !globalSuspended ? 'var(--color-feedback-success)' : 'var(--color-context-track)' }} />
            <span>{tierLabel}</span>
          </div>
          <div className="flex items-center gap-3 pt-0.5">
            {watch && !watch.expired && (watch.suspended
              ? <a className="text-xs text-text-link hover:underline" onClick={() => onWatch('resume')}>{t('docs.watch.watchResume')}</a>
              : <a className="text-xs text-text-link hover:underline" onClick={() => onWatch('suspend')}>{t('docs.watch.watchSuspend')}</a>)}
            {watch && watch.mode === 'apply_scoped' && <a className="text-xs text-text-link hover:underline" onClick={() => onWatch('reply_only')}>{t('docs.watch.watchReply')}</a>}
            {watch && <a className="text-xs text-red-600 hover:underline" onClick={() => onWatch('off')} data-testid="doc-workbench-watch-off">{t('docs.workbench.revoke')}</a>}
          </div>
        </div>
      )}
    </aside>
  );
}
