/**
 * 文档工作台（release §14）：打开一份纳管文档时替换会话工作区。
 * 主列 = 标签栏 + 主界面（平台编辑器 iframe / md 编辑器）+ 底部聊天条；右栏 = 回执 / 聊天历史 / 状态。
 */
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useChatStore } from '../../stores/chatStore';
import { useDocWorkbenchStore } from '../../stores/docWorkbenchStore';
import { webClient, webRequest } from '../../services/webClient';
import { receiptAnchor, receiptsFromExecutions, type ReceiptRow } from '../../features/clouddoc/receipts';
import { TabStrip } from './TabStrip';
import { DocFrame } from './DocFrame';
import { MarkdownEditor } from './MarkdownEditor';
import { ChatStrip, type ComposerProps } from './ChatStrip';
import { SideRail, type WatchInfo } from './SideRail';
import './DocWorkbench.css';

// The gateway pushes clouddoc.receipts_changed when the ledger file moves; the
// poll survives only as a slow fallback for a dropped frame.
const POLL_MS = 60_000;

type WatchListPayload = { global_suspended?: boolean; watches?: { doc_id: string; mode: string; suspended: boolean; expires_at?: number | null; expired?: boolean; revoked?: boolean }[] };

export function DocWorkbench({ composer }: { composer: ComposerProps }) {
  const wb = useDocWorkbenchStore();
  const sid = useChatStore((s) => s.activeSessionId) ?? '';
  const executions = useChatStore((s) => s.runtimes[sid]?.toolExecutions);
  const tab = useMemo(() => wb.tabs.find((t) => t.docId === wb.activeDocId) ?? null, [wb.tabs, wb.activeDocId]);
  const [receipts, setReceipts] = useState<Record<string, ReceiptRow[]>>({});
  const [watches, setWatches] = useState<Record<string, WatchInfo>>({});
  const [globalSuspended, setGlobalSuspended] = useState(false);
  const [mdHighlight, setMdHighlight] = useState<[number, number] | null>(null);

  // Receipts for every open tab: the focused one to show, the others to count
  // as unread. Polling, since no push event exists for the ledger yet.
  const refresh = useCallback(async () => {
    const ids = useDocWorkbenchStore.getState().tabs.map((t) => t.docId);
    const next: Record<string, ReceiptRow[]> = {};
    await Promise.all(ids.map(async (id) => {
      try {
        const out = await webRequest<{ receipts?: ReceiptRow[] }>('clouddoc.receipts', { doc_id: id, limit: 50 });
        next[id] = out?.receipts ?? [];
      } catch {
        next[id] = receipts[id] ?? [];
      }
    }));
    setReceipts(next);
    for (const id of ids) {
      const applied = (next[id] ?? []).filter((r) => r.status !== 'pending').map((r) => r.receipt_id);
      useDocWorkbenchStore.getState().noteReceipts(id, applied);
    }
    try {
      const w = await webRequest<WatchListPayload>('clouddoc.watch_list');
      const map: Record<string, WatchInfo> = {};
      for (const it of w?.watches ?? []) {
        if (it.revoked) continue;
        const lapsed = !!it.expired || (it.expires_at != null && it.expires_at * 1000 <= Date.now());
        map[it.doc_id] = { mode: it.mode, suspended: !!it.suspended, expires_at: it.expires_at ?? null, expired: lapsed };
      }
      setWatches(map);
      setGlobalSuspended(!!w?.global_suspended);
    } catch { /* keep what we had */ }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wb.tabs.length]);

  const executionCount = executions ? executions.size : 0;
  useEffect(() => { void refresh(); }, [refresh, wb.activeDocId, executionCount]);
  useEffect(() => {
    const id = window.setInterval(() => { void refresh(); }, POLL_MS);
    return () => window.clearInterval(id);
  }, [refresh]);
  useEffect(() => webClient.on('clouddoc.receipts_changed', () => { void refresh(); }), [refresh]);

  const tiers = useMemo(() => {
    const out: Record<string, string | undefined> = {};
    for (const t of wb.tabs) out[t.docId] = watches[t.docId] && !watches[t.docId]?.expired ? watches[t.docId]?.mode : undefined;
    return out;
  }, [wb.tabs, watches]);

  // Locate: markdown gets a line range from the receipt's edits; a platform frame
  // reloads (anchors are best-effort and documented as such).
  const locateReceipt = useCallback((r: ReceiptRow) => {
    const doc = wb.tabs.find((t) => t.docId === r.doc_id);
    if (!doc) return;
    wb.activate(r.doc_id);
    if (doc.kind === 'markdown') {
      const text = r.edits?.[0]?.new || '';
      // The receipt carries the written text, not its position; the current text
      // comes through the same read the editor uses, and the range is found in it.
      void webRequest<{ result: string; text?: string }>('clouddoc.read_doc', { doc_id: r.doc_id }).then((out) => {
        const body = out?.text ?? '';
        const at = text ? body.indexOf(text) : -1;
        if (at < 0) { setMdHighlight(null); return; }
        const start = body.slice(0, at).split('\n').length;
        const end = start + text.split('\n').length - 1;
        setMdHighlight([start, end]);
      });
      return;
    }
    setMdHighlight(null);
    // A sheet or deck receipt carries the platform's own URL fragment; the frame
    // reloads on it. A document receipt carries none and the frame just reloads.
    wb.requestLocate(r.doc_id, r.receipt_id, (r.edits || []).map((e) => e.region || '').filter(Boolean), receiptAnchor(r));
  }, [wb]);

  const locateById = useCallback((docId: string, receiptId: string) => {
    const r = (receipts[docId] ?? []).find((x) => x.receipt_id === receiptId);
    if (r) locateReceipt(r);
    else wb.activate(docId);
  }, [receipts, locateReceipt, wb]);

  // A receipt this session just produced lands in the rail without waiting for the poll.
  const ownReceipts = useMemo(() => receiptsFromExecutions(executions ? executions.values() : undefined), [executions]);
  useEffect(() => { if (ownReceipts.length) void refresh(); }, [ownReceipts.length, refresh]);

  const setWatch = useCallback(async (mode: 'off' | 'reply_only' | 'apply_scoped' | 'suspend' | 'resume') => {
    if (!tab) return;
    if (mode === 'suspend' || mode === 'resume') {
      await webRequest(mode === 'suspend' ? 'clouddoc.watch_suspend' : 'clouddoc.watch_resume', { doc_id: tab.docId });
    } else {
      await webRequest('clouddoc.watch_set', { doc_id: tab.docId, mode });
    }
    void refresh();
  }, [tab, refresh]);

  const [frameNonce, setFrameNonce] = useState(0);
  const nonce = (tab ? wb.reloadNonce[tab.docId] ?? 0 : 0) + frameNonce + (wb.locate && wb.locate.docId === tab?.docId ? wb.locate.nonce : 0);

  if (!wb.open || !tab) return null;
  const unreadTotal = wb.tabs.reduce((a, t) => a + t.unread, 0);

  return (
    <div className="doc-workbench" data-testid="doc-workbench">
      <div className="doc-workbench__main">
        <TabStrip
          tabs={wb.tabs}
          activeDocId={wb.activeDocId}
          tiers={tiers}
          railVisible={wb.railVisible}
          chatVisible={wb.chatVisible}
          canOpenExternal={!!tab.url && tab.url.startsWith('http')}
          onActivate={wb.activate}
          onClose={wb.closeTab}
          onOpenExternal={() => { if (tab.url) window.open(tab.url, '_blank', 'noopener'); }}
          onReload={() => setFrameNonce((n) => n + 1)}
          onToggleRail={wb.toggleRail}
          onToggleChat={wb.toggleChat}
          onExit={wb.exit}
        />
        {tab.kind === 'markdown' ? (
          <MarkdownEditor tab={tab} nonce={nonce} highlightLines={mdHighlight} onSaved={() => void refresh()} />
        ) : (
          <DocFrame
            tab={tab}
            nonce={nonce}
            anchor={wb.locate && wb.locate.docId === tab.docId ? wb.locate.anchor : ''}
            alwaysNewTab={!!wb.alwaysNewTab[tab.provider]}
            onAlwaysNewTab={(v) => wb.setAlwaysNewTab(tab.provider, v)}
            onReload={() => setFrameNonce((n) => n + 1)}
          />
        )}
        <ChatStrip
          composer={composer}
          visible={wb.chatVisible}
          onHide={wb.toggleChat}
          onShow={wb.toggleChat}
          unreadReceipts={unreadTotal}
          onLocate={locateById}
          onHistory={() => { if (!wb.railVisible) wb.toggleRail(); wb.setRailTab('history'); }}
        />
      </div>
      {wb.railVisible && (
        <SideRail
          tab={tab}
          tabs={wb.tabs}
          railTab={wb.railTab}
          receipts={receipts[tab.docId] ?? []}
          watch={watches[tab.docId]}
          globalSuspended={globalSuspended}
          onTab={wb.setRailTab}
          onRefresh={() => void refresh()}
          onLocate={locateReceipt}
          onJump={wb.activate}
          onWatch={(m) => void setWatch(m)}
        />
      )}
    </div>
  );
}
