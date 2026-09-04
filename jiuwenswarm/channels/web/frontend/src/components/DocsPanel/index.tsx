/**
 * The Docs panel -- the UI for cloud-document co-editing.
 *
 * The layout matches Channel Management in structure and proportion: connections in
 * the left column at minmax(340,430), detail filling the remaining width on the
 * right, and Refresh at the top right of the detail header, where Channel puts its
 * own.
 *
 * The wholly empty state, with no connections at all, keeps the same skeleton: the
 * left column holds only an "add connection" placeholder card and the right column
 * carries the guidance. A user sees the shape this page will take before configuring
 * anything, so where they learn things are does not change once they have.
 */
import type { ReactNode } from 'react';
import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { webRequest } from '../../services/webClient';
import { requestOpenDoc } from '../../features/clouddoc/openDocSignal';
import { RECEIPT_OP_KEY, RECEIPT_STATUS_KEY, type ReceiptRow } from '../../features/clouddoc/receipts';
import ConfirmDialog from '../CronPanel/ConfirmDialog';
import SimpleSelect from '../CronPanel/SimpleSelect';

interface DocRow {
  doc_id: string;
  url: string;
  title: string;
  checked_at?: number | null;
  status: 'ok' | 'comment_only' | 'frozen' | 'backoff';
  // The document's format. A spreadsheet under management looked exactly like a
  // document in this list, which is how one went unnoticed while it was being polled.
  kind?: string;
  retry_at?: number | null;
  provider?: string;
  provider_name?: string;
  connection_id?: string;
}

interface Connection {
  id: string;
  provider: string;
  provider_name: string;
  agent_address: string;
  agent_display?: string;
  docs_count: number;
  health?: 'ok' | 'attention' | 'down' | 'idle';
  ok?: number;
  attention?: number;
  down?: number;
}

interface ConfPayload {
  enabled: boolean;
  mode?: 'mandate' | 'recorded' | 'direct';
  agent_address?: string;
  approve_word?: string;
  keep_word?: string;
  connections?: Connection[];
}

interface AddResult {
  result: 'ok' | 'exists' | 'comment_only' | 'not_shared' | 'unknown' | 'invalid' | 'no_connection';
  detail?: string;
  title?: string;
  connection_id?: string;
}

// Provider to logo asset, following the same rule as ChannelsPanel's logo_src. An
// unregistered provider falls back to a generic document glyph, so a new provider
// without an asset leaves no hole in the layout.
const PROVIDER_LOGOS: Record<string, string> = { google: '/googledocs.svg' };

// One look per format, in the colours the platforms themselves use: a document is
// blue, a spreadsheet green, a deck amber. They shared one icon until now, so a
// spreadsheet in the managed list was indistinguishable from a document -- which is
// how one sat there being polled while the person looking at the list could not tell
// it was there.
//
// Drawn inline rather than from files: only the Docs logo exists as an asset, and a
// per-format set has to cover Feishu too, where the same three formats appear under a
// different brand. A shape the panel owns stays right for both.
const KIND_STYLE: Record<string, { bg: string; fg: string; glyph: 'doc' | 'sheet' | 'deck' | 'file' }> = {
  document: { bg: '#e8f0fe', fg: '#1a73e8', glyph: 'doc' },
  spreadsheet: { bg: '#e6f4ea', fg: '#188038', glyph: 'sheet' },
  presentation: { bg: '#fef7e0', fg: '#e37400', glyph: 'deck' },
  markdown: { bg: '#f1f3f4', fg: '#5f6368', glyph: 'file' },
};

const GLYPHS: Record<string, ReactNode> = {
  doc: (
    <>
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <path d="M14 2v6h6" />
    </>
  ),
  sheet: (
    <>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <path d="M3 10h18M3 15h18M9 4v16M15 4v16" />
    </>
  ),
  deck: (
    // A slide, not a projector screen on a stand. The stand version drew its frame in
    // the top half and a thin pole and base below, which at the size this renders --
    // half of a 26px badge, so about 13 -- merged into a smudge, and left the deck the
    // only glyph whose body was not centred in its box. Sitting beside the document and
    // spreadsheet icons it read as a different kind of thing entirely.
    <>
      <rect x="3" y="5" width="18" height="14" rx="2" />
      <path d="M7 10h10M7 14h6" />
    </>
  ),
  file: (
    <>
      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
      <path d="M14 2v6h6M8 13h8M8 17h5" />
    </>
  ),
};

const DocIcon = ({ px = 32, provider, kind }: { px?: number; provider?: string; kind?: string }) => {
  const style = KIND_STYLE[kind || ''] ?? KIND_STYLE.document;
  // The platform logo is used only where it is still true: it is the Docs logo, and
  // putting it on a spreadsheet says the wrong thing.
  const src = provider && (!kind || kind === 'document') ? PROVIDER_LOGOS[provider] : undefined;
  if (src) {
    return <img src={src} alt="" aria-hidden style={{ height: px, width: px * 0.75 }} className="flex-none object-contain" />;
  }
  return (
    <span
      data-testid="docs-panel-kind-icon"
      data-kind={kind || 'document'}
      title={kind || 'document'}
      className="flex flex-none items-center justify-center rounded-full"
      style={{ height: px, width: px, background: style.bg, color: style.fg }}
    >
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} style={{ height: px / 2, width: px / 2 }}>
        {GLYPHS[style.glyph]}
      </svg>
    </span>
  );
};

const ExtIcon = () => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} className="h-3 w-3 flex-none">
    <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
    <path d="M15 3h6v6" />
    <path d="M10 14 21 3" />
  </svg>
);

function docSubline(d: DocRow, t: (k: string, o?: Record<string, unknown>) => string): string {
  const hm = (ts?: number | null) =>
    ts ? new Date(ts * 1000).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' }) : '';
  switch (d.status) {
    case 'comment_only':
      return t('docs.sub.commentOnly');
    case 'frozen':
      return t('docs.sub.frozen');
    case 'backoff':
      return d.retry_at ? t('docs.sub.backoffAt', { time: hm(d.retry_at) }) : t('docs.sub.backoff');
    default:
      return d.checked_at ? t('docs.sub.checkedAt', { time: hm(d.checked_at) }) : (d.provider_name ?? 'Google Docs');
  }
}

function StatusPill({ status }: { status: DocRow['status'] }) {
  const { t } = useTranslation();
  const styles: Record<DocRow['status'], string> = {
    ok: 'text-green-700 bg-green-50',
    comment_only: 'text-amber-700 bg-amber-50',
    frozen: 'text-gray-500 bg-gray-100',
    backoff: 'text-gray-500 bg-gray-100',
  };
  return (
    <span
      className={`flex-none whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs ${styles[status]}`}
      title={
        status === 'comment_only'
          ? t('docs.status.commentOnlyHint')
          : status === 'frozen' || status === 'backoff'
            ? t('docs.status.frozenHint')
            : undefined
      }
    >
      {t(`docs.status.${status}`)}
    </span>
  );
}

function EmptyIllustration() {
  return (
    <svg viewBox="0 0 88 66" fill="none" stroke="currentColor" strokeWidth={1.6} className="mx-auto h-16 w-20 text-text-muted/50">
      <rect x="18" y="10" width="42" height="52" rx="4" />
      <path d="M26 22h26M26 30h26M26 38h16" />
      <circle cx="64" cy="46" r="13" fill="var(--color-surface-elevated, #fff)" />
      <path d="M64 40v12m-6-6h12" stroke="#2563eb" strokeWidth={2} />
    </svg>
  );
}



export function DocsPanel({ isConnected }: { isConnected: boolean }) {
  const { t } = useTranslation();
  const [conf, setConf] = useState<ConfPayload | null>(null);
  const [docs, setDocs] = useState<DocRow[]>([]);
  const [selectedConn, setSelectedConn] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [addUrl, setAddUrl] = useState('');
  const [addBusy, setAddBusy] = useState(false);
  const [addResult, setAddResult] = useState<AddResult | null>(null);
  // Shared with this account but **comment-only**: adoption skips them because
  // admission would refuse them anyway, so they are shown with the fix instead.
  const [needsEditor, setNeedsEditor] = useState<{ doc_id: string; title: string; url: string }[]>([]);
  // Shared with this account but a type co-editing cannot take (spreadsheets,
  // presentations, uploaded Office files). Listed so "unsupported" and "the share
  // failed" stop looking identical.
  const [unsupported, setUnsupported] = useState<{ title: string; kind: string }[]>([]);
  const [adopted, setAdopted] = useState(0);
  const [copied, setCopied] = useState(false);
  const [menuFor, setMenuFor] = useState<string | null>(null);
  // The history view: which document's receipts are open, and what they said.
  const [historyFor, setHistoryFor] = useState<DocRow | null>(null);
  const [receipts, setReceipts] = useState<ReceiptRow[]>([]);
  const [historyBusy, setHistoryBusy] = useState(false);
  const [historyNote, setHistoryNote] = useState('');
  const [actingOn, setActingOn] = useState<string | null>(null);
  const [refreshedAt, setRefreshedAt] = useState<string>('');
  const [removeTarget, setRemoveTarget] = useState<DocRow | null>(null);
  const [removing, setRemoving] = useState(false);
  const [addConnOpen, setAddConnOpen] = useState(false);
  const [connMode, setConnMode] = useState<'path' | 'upload' | 'saved'>('path');
  // Keys kept on disk by remove_connection. Listed so finding one back is a click,
  // not an ls in a dotfile directory.
  const [savedKeys, setSavedKeys] = useState<
    { filename: string; path: string; client_email: string; in_use: boolean }[]
  >([]);
  const [savedSel, setSavedSel] = useState<string | null>(null);
  const [keyDeleteArm, setKeyDeleteArm] = useState<string | null>(null);
  const [connPath, setConnPath] = useState('');
  const [connJson, setConnJson] = useState<{ name: string; body: string } | null>(null);
  const [connBusy, setConnBusy] = useState(false);
  const [connError, setConnError] = useState<string | null>(null);
  const [removeConnTarget, setRemoveConnTarget] = useState<Connection | null>(null);
  // PR2b: the standing-mandate registry -- per-doc watch level, suspension, backlog.
  // `revoked` is the registry's tombstone (E1): the entry stays after 只读 or
  // 移出纳管 so the adoption policy cannot re-issue silently. Dropped here, a revoked
  // row kept its 操作权/建议权 label on the next load (measured 2026-09-03).
  type WatchRow = { mode: string; suspended: boolean; expires_at?: number | null; expired?: boolean; revoked?: boolean };  // revoked rows are skipped, never stored
  const [watches, setWatches] = useState<Record<string, WatchRow>>({});
  const [globalSuspended, setGlobalSuspended] = useState(false);
  const [backlogCount, setBacklogCount] = useState(0);
  // Two-click confirmations: Operate is the heavy rung (policy signature), and the
  // kill switch revokes everything -- both follow the keyDeleteArm pattern.
  const [armApply, setArmApply] = useState<string | null>(null);
  const [armKill, setArmKill] = useState(false);
  // D21: the deployment's Direct/Mandate switch. Downgrading is explicit
  // (two-click, same pattern as the kill switch) and the direct state keeps a
  // standing banner -- nobody runs bare without knowing.
  const [armDirect, setArmDirect] = useState(false);
  // The one-table view: client-side filters and the adoption target.
  const [filterConn, setFilterConn] = useState('');
  const [filterTier, setFilterTier] = useState('');
  const [filterKind, setFilterKind] = useState('');
  const [addConnId, setAddConnId] = useState('');
  const setMode = useCallback(async (mode: 'mandate' | 'direct') => {
    await webRequest('clouddoc.set_mode', { mode });
    setArmDirect(false);
    await reload();
  }, []);
  // A chat reference chip may have asked for a document before this panel
  // mounted; the latch holds the id either way, and the effect below waits for
  // the row to exist before opening its history.

  const reload = useCallback(async () => {
    try {
      const [c, l] = await Promise.all([
        webRequest<ConfPayload>('clouddoc.get_conf'),
        webRequest<{ enabled: boolean; docs: DocRow[] }>('clouddoc.list_docs'),
      ]);
      setConf(c);
      setDocs(l.docs ?? []);
      setSelectedConn((prev) => prev ?? c.connections?.[0]?.id ?? null);
      setRefreshedAt(new Date().toLocaleTimeString('en-GB'));
      try {
        const w = await webRequest<{
          global_suspended: boolean;
          watches: { doc_id: string; mode: string; suspended: boolean; expires_at?: number | null; expired?: boolean; revoked?: boolean }[];
        }>('clouddoc.watch_list');
        const map: Record<string, WatchRow> = {};
        for (const it of w.watches ?? []) {
          // A revoked entry is no mandate at all: the row reads 只读 like an
          // unregistered one. Expiry is judged here as well as by the server, so
          // the row does not read "剩 0 天" between the deadline and the next poll.
          if (it.revoked) continue;
          const lapsed = !!it.expired || (it.expires_at != null && it.expires_at * 1000 <= Date.now());
          map[it.doc_id] = { mode: it.mode, suspended: !!it.suspended, expires_at: it.expires_at ?? null, expired: lapsed };
        }
        setWatches(map);
        setGlobalSuspended(!!w.global_suspended);
        // Live API work on the backend: never hold the panel's first paint on it.
        void webRequest<{ count: number }>('clouddoc.backlog')
          .then((b) => setBacklogCount(b.count ?? 0))
          .catch(() => undefined);
      } catch {
        /* the watch registry answers only when the gateway ships PR2b */
      }
    } catch {
      setConf({ enabled: false });
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (isConnected) void reload();
  }, [isConnected, reload]);

  const conns = conf?.connections ?? [];
  const conn = conns.find((c) => c.id === selectedConn) ?? conns[0] ?? null;
  const connDocs = docs.filter((d) => !d.connection_id || !conn || d.connection_id === conn.id);

  const setWatchLevel = useCallback(
    async (docId: string, mode: 'off' | 'reply_only' | 'apply_scoped') => {
      try {
        if (mode === 'off') await webRequest('clouddoc.watch_revoke', { doc_id: docId });
        else await webRequest('clouddoc.watch_set', { doc_id: docId, mode });
      } finally {
        setMenuFor(null);
        setArmApply(null);
        await reload();
      }
    },
    [reload],
  );

  const toggleSuspend = useCallback(
    async (docId: string, suspended: boolean) => {
      await webRequest(suspended ? 'clouddoc.watch_resume' : 'clouddoc.watch_suspend', { doc_id: docId });
      setMenuFor(null);
      await reload();
    },
    [reload],
  );

  // The audit view (E1): granted minus used, shown at the renewal moment.
  const [usageFor, setUsageFor] = useState<DocRow | null>(null);
  const [usage, setUsage] = useState<Record<string, unknown> | null>(null);
  const [usageBusy, setUsageBusy] = useState(false);
  const openUsage = useCallback(async (doc: DocRow) => {
    setMenuFor(null);
    setUsageFor(doc);
    setUsage(null);
    setUsageBusy(true);
    try {
      const out = await webRequest<Record<string, unknown>>('clouddoc.watch_usage', { doc_id: doc.doc_id });
      setUsage(out ?? null);
    } catch {
      setUsage(null);
    } finally {
      setUsageBusy(false);
    }
  }, []);
  const renew = useCallback(async (doc: DocRow, permanent: boolean) => {
    const w = watches[doc.doc_id];
    if (!w) return;
    await webRequest('clouddoc.watch_set', {
      doc_id: doc.doc_id, mode: w.mode, ...(permanent ? { permanent: true } : {}),
    });
    setUsageFor(null);
    await reload();
  }, [watches, reload]);

  const openHistory = useCallback(async (doc: DocRow) => {
    setMenuFor(null);
    setHistoryFor(doc);
    setHistoryNote('');
    setHistoryBusy(true);
    try {
      const out = await webRequest<{ receipts?: ReceiptRow[] }>('clouddoc.receipts', {
        doc_id: doc.doc_id,
        limit: 50,
      });
      setReceipts(out?.receipts ?? []);
    } catch (e) {
      setReceipts([]);
      setHistoryNote(String(e));
    } finally {
      setHistoryBusy(false);
    }
  }, []);


  // Revert and un-highlight both answer with ok plus a detail, and both change what
  // the feed should show, so the outcome is surfaced and the feed re-read rather than
  // patched in place -- the store is the truth about a receipt's status.
  const actOnReceipt = useCallback(
    async (method: 'clouddoc.unhighlight', receiptId: string) => {
      if (!historyFor) return;
      setActingOn(receiptId);
      setHistoryNote('');
      try {
        // A revert on Feishu walks several CLI round-trips (read, write, read-back
        // verify, thread notify); the 15s default timed out while the backend
        // finished, and the user saw an error over a revert that had landed.
        const out = await webRequest<{ ok?: boolean; detail?: string }>(
          method,
          { receipt_id: receiptId },
          { timeoutMs: 60000 },
        );
        if (out && out.ok === false) setHistoryNote(out.detail || t('docs.history.failed'));
      } catch (e) {
        // The request failing does not mean the action failed -- a timeout can race a
        // completed revert. The refresh below shows the receipt's true status either
        // way; the note says so instead of presenting a raw error as the outcome.
        setHistoryNote(t('docs.history.actionUnconfirmed'));
        console.warn('[docs] receipt action error', e);
      } finally {
        try {
          const fresh = await webRequest<{ receipts?: ReceiptRow[] }>('clouddoc.receipts', {
            doc_id: historyFor.doc_id,
            limit: 50,
          });
          setReceipts(fresh?.receipts ?? []);
        } catch { /* the feed keeps its last state */ }
        setActingOn(null);
      }
    },
    [historyFor, t],
  );

  const toggleGlobalSuspend = useCallback(async () => {
    await webRequest(globalSuspended ? 'clouddoc.watch_resume_all' : 'clouddoc.watch_suspend_all');
    await reload();
  }, [globalSuspended, reload]);

  const killSwitch = useCallback(async () => {
    if (!armKill) {
      setArmKill(true);
      setTimeout(() => setArmKill(false), 4000);
      return;
    }
    setArmKill(false);
    await webRequest('clouddoc.watch_revoke_all');
    await reload();
  }, [armKill, reload]);

  // Sharing a document with the account is what puts it under management -- no second
  // confirmation here, because sharing is already a deliberate act performed in Google's
  // own interface. Returns how many were adopted so the caller knows to reload the list.
  const syncShared = useCallback(async (connId?: string | null): Promise<number> => {
    try {
      const out = await webRequest<{
        adopted: { doc_id: string; title: string }[];
        needs_editor: { doc_id: string; title: string; url: string }[];
        unsupported: { title: string; kind: string }[];
      }>('clouddoc.sync_shared_docs', { connection_id: connId ?? null });
      setNeedsEditor(out?.needs_editor ?? []);
      setUnsupported(out?.unsupported ?? []);
      setAdopted(out?.adopted?.length ?? 0);
      return out?.adopted?.length ?? 0;
    } catch {
      setNeedsEditor([]);     // a convenience; failing it must not break the panel
      setUnsupported([]);
      return 0;
    }
  }, []);

  // Opening the panel adopts whatever has been shared since it was last open, so the
  // documents are simply there. list_docs stays API-free; this one call is the deliberate
  // exception, and it is what makes sharing the only step a user performs.
  useEffect(() => {
    if (!isConnected || !conn?.id) return;
    void syncShared(conn.id).then((n) => { if (n > 0) void reload(); });
  }, [isConnected, conn?.id, syncShared, reload]);

  const copyAddress = () => {
    if (!conn?.agent_address) return;
    void navigator.clipboard.writeText(conn.agent_address).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    });
  };

  const handleAdd = async () => {
    const url = addUrl.trim();
    if (!url || addBusy) return;
    setAddBusy(true);
    setAddResult(null);
    try {
      const addTo = addConnId || conns[0]?.id;
      const out = await webRequest<AddResult>('clouddoc.add_doc', { url, connection_id: addTo });
      if (out?.result === 'ok') await syncShared(addTo);
      setAddResult(out);
      if (out.result === 'ok') {
        setAddUrl('');
        await reload();
      }
    } catch (e) {
      setAddResult({ result: 'unknown', detail: String(e) });
    } finally {
      setAddBusy(false);
    }
  };

  // Refresh is repair plus adoption: re-check every watched document, then pull in
  // whatever has been shared since. Repair runs first so the list it walks is the one
  // the user was looking at; newly adopted documents were just probed by the listing.
  const handleRefresh = async () => {
    if (refreshing) return;
    setRefreshing(true);
    try {
      for (const d of connDocs) {
        await webRequest('clouddoc.update_doc', { doc_id: d.doc_id }).catch(() => {});
      }
      await syncShared(conn?.id);
      await reload();
    } finally {
      setRefreshing(false);
    }
  };

  const handleRemove = async () => {
    if (!removeTarget) return;
    setRemoving(true);
    try {
      await webRequest('clouddoc.remove_doc', { doc_id: removeTarget.doc_id }).catch(() => {});
      await reload();
    } finally {
      setRemoving(false);
      setRemoveTarget(null);
    }
  };

  // (row titles link out directly in the table view)

  const resetConnDialog = () => {
    setAddConnOpen(false);
    setConnMode('path');
    setConnPath('');
    setConnJson(null);
    setConnError(null);
  };

  const loadSavedKeys = useCallback(async () => {
    try {
      const out = await webRequest<{ keys: typeof savedKeys }>('clouddoc.list_keys');
      setSavedKeys(out?.keys ?? []);
    } catch {
      setSavedKeys([]);
    }
  }, []);

  const deleteSavedKey = useCallback(async (filename: string) => {
    try {
      await webRequest('clouddoc.delete_key', { filename });
    } finally {
      setKeyDeleteArm(null);
      void loadSavedKeys();
    }
  }, [loadSavedKeys]);

  const handleAddConnection = async () => {
    if (connBusy) return;
    const params: Record<string, unknown> = {};
    if (connMode === 'path') {
      if (!connPath.trim()) return;
      params.credentials_path = connPath.trim();
    } else if (connMode === 'saved') {
      const k = savedKeys.find((x) => x.filename === savedSel);
      if (!k) return;
      params.credentials_path = k.path;
    } else {
      if (!connJson) return;
      params.credentials_json = connJson.body;
      params.filename = connJson.name.replace(/\.json$/i, '');
    }
    setConnBusy(true);
    setConnError(null);
    try {
      const out = await webRequest<{ result: string; detail?: string; connection?: Connection }>(
        'clouddoc.add_connection',
        params,
      );
      if (out.result === 'ok') {
        resetConnDialog();
        await reload();
        if (out.connection) setSelectedConn(out.connection.id);
      } else {
        // A payload without a result at all -- the shape a disabled backend returns --
        // would otherwise render the missing key's own name into the dialog.
        setConnError(
          t(`docs.connErr.${out.result ?? 'unknown'}`, {
            detail: out.detail ?? '',
            defaultValue: t('docs.connErr.unknown', { detail: out.detail ?? '' }),
          }),
        );
      }
    } catch (e) {
      setConnError(String(e));
    } finally {
      setConnBusy(false);
    }
  };

  const handleRemoveConnection = async () => {
    if (!removeConnTarget) return;
    setRemoving(true);
    try {
      await webRequest('clouddoc.remove_connection', { connection_id: removeConnTarget.id }).catch(() => {});
      setSelectedConn(null);
      await reload();
    } finally {
      setRemoving(false);
      setRemoveConnTarget(null);
    }
  };

  if (loading) {
    return (
      <div className="flex h-full w-full flex-col px-6 py-4">
        <div className="h-7 w-24 animate-pulse rounded-md bg-bg-muted" />
        <div className="mt-2 h-4 w-64 animate-pulse rounded-md bg-bg-muted" />
        <div className="mt-4 grid flex-1 gap-4" style={{ gridTemplateColumns: 'minmax(340px, 430px) 1fr' }}>
          <div className="animate-pulse rounded-xl border border-border bg-bg-muted/60" />
          <div className="animate-pulse rounded-xl border border-border bg-bg-muted/60" />
        </div>
      </div>
    );
  }

  const hasConn = conns.length > 0;

  return (
    <div className="flex h-full w-full flex-col px-6 py-4" onClick={() => setMenuFor(null)}>
      <h1 className="text-[22px] font-semibold">{t('docs.title')}</h1>
      <p className="mt-0.5 text-[13px] text-text-muted">{t('docs.subtitle')}</p>

      {conf?.mode === 'direct' ? (
        <div
          data-testid="docs-mode-banner"
          className="mt-3 flex items-center justify-between gap-3 rounded-lg border border-amber-300 bg-amber-50 px-4 py-2.5 text-[13px] text-amber-900"
        >
          <span>{t('docs.mode.directBanner')}</span>
          <button
            onClick={() => void setMode('mandate')}
            className="flex-none rounded-md border border-amber-400 px-3 py-1 font-medium hover:bg-amber-100"
          >
            {t('docs.mode.restoreMandate')}
          </button>
        </div>
      ) : conf?.mode === 'mandate' ? (
        <div className="mt-2 flex items-center gap-2 text-[12px] text-text-muted">
          <span>{t('docs.mode.mandateNote')}</span>
          <button
            data-testid="docs-mode-downgrade"
            onClick={() => {
              if (!armDirect) {
                setArmDirect(true);
                setTimeout(() => setArmDirect(false), 5000);
                return;
              }
              void setMode('direct');
            }}
            className={`rounded-md border px-2 py-0.5 ${armDirect ? 'border-amber-400 text-amber-700' : 'border-border hover:bg-bg-hover'}`}
          >
            {armDirect ? t('docs.mode.confirmDirect') : t('docs.mode.goDirect')}
          </button>
        </div>
      ) : null}

      <div className="mt-3.5 flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border border-border bg-card">
        {/* ── 工具条：过滤 + 全局动作（连接管理在 Settings，这里只剩全局与归属）── */}
        <div className="flex flex-wrap items-center gap-2 border-b border-border px-4 py-2.5">
          {conns.length > 1 && (
            <select
              value={filterConn}
              onChange={(e) => setFilterConn(e.target.value)}
              className="rounded-md border border-border bg-card px-2 py-1 text-xs"
              data-testid="docs-filter-conn"
            >
              <option value="">{t('docs.table.allConns')}</option>
              {conns.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.provider_name} · {c.agent_display || (c.agent_address || c.id).split('@')[0]}
                </option>
              ))}
            </select>
          )}
          <select
            value={filterKind}
            onChange={(e) => setFilterKind(e.target.value)}
            className="rounded-md border border-border bg-card px-2 py-1 text-xs"
            data-testid="docs-filter-kind"
          >
            <option value="">{t('docs.table.allKinds')}</option>
            <option value="document">{t('docs.kind.document')}</option>
            <option value="spreadsheet">{t('docs.kind.spreadsheet')}</option>
            <option value="presentation">{t('docs.kind.presentation')}</option>
            <option value="markdown">{t('docs.kind.markdown')}</option>
            <option value="file">{t('docs.kind.file')}</option>
          </select>
          <select
            value={filterTier}
            onChange={(e) => setFilterTier(e.target.value)}
            className="rounded-md border border-border bg-card px-2 py-1 text-xs"
            data-testid="docs-filter-tier"
          >
            <option value="">{t('docs.table.allTiers')}</option>
            <option value="off">{t('docs.watch.watchOff')}</option>
            <option value="reply_only">{t('docs.watch.watchReply')}</option>
            <option value="apply_scoped">{t('docs.watch.watchApply')}</option>
          </select>
          {backlogCount > 0 && (
            <span className="rounded-full bg-amber-50 px-2.5 py-0.5 text-[11px] text-amber-700">
              {t('docs.backlogBanner', { count: backlogCount })}
            </span>
          )}
          <span className="flex-1" />
          {hasConn && (
            <>
              <button
                onClick={() => void toggleGlobalSuspend()}
                className="rounded-md border border-border px-2.5 py-1 text-xs hover:bg-bg-hover"
              >
                {globalSuspended ? t('docs.watch.globalResume') : t('docs.watch.globalSuspend')}
              </button>
              <button
                onClick={() => void killSwitch()}
                className={`rounded-md border px-2.5 py-1 text-xs ${armKill ? 'border-red-400 text-red-600' : 'border-border text-text-muted hover:bg-bg-hover'}`}
              >
                {armKill ? t('docs.watch.killSwitchConfirm') : t('docs.watch.killSwitch')}
              </button>
              <button
                onClick={() => void handleRefresh()}
                disabled={refreshing}
                className="rounded-md border border-border px-2.5 py-1 text-xs hover:bg-bg-hover"
                data-testid="docs-refresh"
              >
                {refreshing ? '…' : t('docs.refresh')}
              </button>
            </>
          )}
        </div>

        {hasConn ? (
          <>
            <div className="min-h-0 flex-1 overflow-auto">
              <table className="w-full border-collapse text-[13px]">
                <thead className="sticky top-0 z-[1] bg-card">
                  <tr className="border-b border-border text-left text-[11.5px] uppercase tracking-wide text-text-muted">
                    <th className="px-4 py-2 font-medium">{t('docs.table.colDoc')}</th>
                    <th className="px-3 py-2 font-medium">{t('docs.table.colKind')}</th>
                    {conns.length > 1 && <th className="px-3 py-2 font-medium">{t('docs.table.colConn')}</th>}
                    <th className="px-3 py-2 font-medium">{t('docs.table.colStatus')}</th>
                    <th className="px-3 py-2 font-medium">{t('docs.table.colTier')}</th>
                    <th className="px-3 py-2 font-medium">{t('docs.table.colActivity')}</th>
                    <th className="w-10 px-2 py-2" />
                  </tr>
                </thead>
                <tbody>
                  {docs
                    .filter((d) => !filterConn || d.connection_id === filterConn)
                    .filter((d) => !filterKind || (d.kind || 'document') === filterKind)
                    .filter((d) => {
                      if (!filterTier) return true;
                      const w = watches[d.doc_id];
                      return filterTier === 'off' ? !w : w?.mode === filterTier;
                    })
                    .sort((a, b) => (b.checked_at ?? 0) - (a.checked_at ?? 0))
                    .map((d) => {
                      const w = watches[d.doc_id];
                      const cconn = conns.find((c) => c.id === d.connection_id);
                      const tierLabel = !w
                        ? t('docs.watch.watchOff')
                        : w.expired
                          ? t('docs.watch.watchExpired')
                          : w.suspended || globalSuspended
                            ? t('docs.watch.watchSuspended')
                            : w.mode === 'apply_scoped'
                              ? t('docs.watch.watchApply')
                              : t('docs.watch.watchReply');
                      const tierCls = !w
                        ? 'bg-bg-hover text-text-muted'
                        : w.expired || w.suspended || globalSuspended
                          ? 'bg-amber-50 text-amber-700'
                          : w.mode === 'apply_scoped'
                            ? 'bg-red-50 text-red-700'
                            : 'bg-blue-50 text-blue-700';
                      const daysLeft =
                        w?.expires_at && !w.expired
                          ? Math.max(0, Math.ceil((w.expires_at * 1000 - Date.now()) / 86400000))
                          : null;
                      return (
                        <tr key={d.doc_id} className="border-b border-border/60 hover:bg-bg-hover/40" data-testid="docs-table-row">
                          <td className="max-w-[340px] px-4 py-2">
                            <span className="flex items-center gap-2.5">
                              <DocIcon px={26} provider={d.provider} kind={d.kind} />
                              <span className="min-w-0">
                                {d.url && d.url.startsWith('http') ? (
                                  <span className="flex items-center gap-1.5 truncate font-medium">
                                    <button
                                      type="button"
                                      className="truncate text-left hover:underline"
                                      title={t('docs.workbench.openHere')}
                                      onClick={() => requestOpenDoc(d.doc_id)}
                                      data-testid="docs-table-open-workbench"
                                    >
                                      {d.title || d.doc_id}
                                    </button>
                                    <a href={d.url} target="_blank" rel="noreferrer" title={t('docs.workbench.openExternal')} className="flex items-center">
                                      <ExtIcon />
                                    </a>
                                  </span>
                                ) : (
                                  <span
                                    className="block truncate font-medium"
                                    title={t('docs.linkUnknown')}
                                  >
                                    {d.title || d.doc_id}
                                  </span>
                                )}
                                <span className="block truncate text-[11px] text-text-muted">{docSubline(d, t)}</span>
                              </span>
                            </span>
                          </td>
                          <td className="whitespace-nowrap px-3 py-2 text-xs text-text-muted">
                            {t(`docs.kind.${d.kind || 'document'}`, d.kind || 'document')}
                          </td>
                          {conns.length > 1 && (
                            <td className="whitespace-nowrap px-3 py-2 text-xs text-text-muted">
                              <span className="inline-flex items-center gap-1.5">
                                {PROVIDER_LOGOS[d.provider ?? ''] ? (
                                  <img src={PROVIDER_LOGOS[d.provider ?? '']} alt={d.provider_name} className="h-3.5 w-3.5 object-contain" />
                                ) : (
                                  <span className="rounded bg-bg-muted px-1 text-[10px]">{d.provider_name}</span>
                                )}
                                {cconn?.agent_display || (cconn?.agent_address || '').split('@')[0] || d.connection_id}
                              </span>
                            </td>
                          )}
                          <td className="whitespace-nowrap px-3 py-2"><StatusPill status={d.status} /></td>
                          <td className="whitespace-nowrap px-3 py-2">
                            <span className={`rounded-md px-1.5 py-0.5 text-[11px] font-medium ${tierCls}`}>{tierLabel}</span>
                            {daysLeft !== null && (
                              <span className="ml-1.5 text-[11px] text-text-muted">{t('docs.table.daysLeft', { count: daysLeft })}</span>
                            )}
                          </td>
                          <td className="whitespace-nowrap px-3 py-2 font-mono text-[11px] text-text-muted">
                            {d.checked_at ? new Date(d.checked_at * 1000).toLocaleString(undefined, { month: 'numeric', day: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—'}
                          </td>
                          <td className="px-2 py-2">
                            <span className="relative block" onClick={(e) => e.stopPropagation()}>
                              <button
                                onClick={() => setMenuFor(menuFor === d.doc_id ? null : d.doc_id)}
                                className="rounded-md px-1.5 py-0.5 text-text-muted hover:bg-bg-hover hover:text-text"
                                aria-haspopup="menu"
                                aria-expanded={menuFor === d.doc_id}
                              >
                                ⋯
                              </button>
                              {menuFor === d.doc_id && (
                                <span className="absolute right-0 top-7 z-10 block w-44 rounded-lg border border-border bg-card py-1 shadow-lg">
                                  {(['off', 'reply_only', 'apply_scoped'] as const).map((m) => {
                                    const current = (!w && m === 'off') || w?.mode === m;
                                    const label =
                                      m === 'off'
                                        ? t('docs.watch.watchOff')
                                        : m === 'reply_only'
                                          ? t('docs.watch.watchReply')
                                          : t('docs.watch.watchApply');
                                    return (
                                      <button
                                        key={m}
                                        onClick={() => {
                                          if (m === 'apply_scoped' && armApply !== d.doc_id) {
                                            setArmApply(d.doc_id);
                                            setTimeout(() => setArmApply(null), 5000);
                                            return;
                                          }
                                          void setWatchLevel(d.doc_id, m);
                                        }}
                                        className={`block w-full px-3 py-1.5 text-left text-xs hover:bg-bg-hover ${current ? 'font-semibold text-[#2563eb]' : ''}`}
                                      >
                                        {m === 'apply_scoped' && armApply === d.doc_id
                                          ? t('docs.watch.watchApplyConfirm')
                                          : label}
                                      </button>
                                    );
                                  })}
                                  {w && (
                                    <button
                                      onClick={() => void toggleSuspend(d.doc_id, w.suspended)}
                                      className="block w-full border-t border-border px-3 py-1.5 text-left text-xs hover:bg-bg-hover"
                                    >
                                      {w.suspended ? t('docs.watch.watchResume') : t('docs.watch.watchSuspend')}
                                    </button>
                                  )}
                                  {w && (
                                    <button
                                      data-testid="docs-panel-usage-open"
                                      onClick={() => void openUsage(d)}
                                      className="block w-full border-t border-border px-3 py-1.5 text-left text-xs hover:bg-bg-hover"
                                    >
                                      {t('docs.usage.open')}
                                    </button>
                                  )}
                                  <button
                                    data-testid="docs-panel-history-open"
                                    onClick={() => void openHistory(d)}
                                    className="block w-full border-t border-border px-3 py-1.5 text-left text-xs hover:bg-bg-hover"
                                  >
                                    {t('docs.history.open')}
                                  </button>
                                  <button
                                    onClick={() => {
                                      setMenuFor(null);
                                      setRemoveTarget(d);
                                    }}
                                    className="block w-full border-t border-border px-3 py-1.5 text-left text-xs text-red-600 hover:bg-bg-hover"
                                  >
                                    {t('docs.remove')}
                                  </button>
                                </span>
                              )}
                            </span>
                          </td>
                        </tr>
                      );
                    })}
                </tbody>
              </table>
            </div>

            {/* ── 表底：纳管入口（多连接带身份选择）+ 指路 ── */}
            <div className="border-t border-border px-4 py-3">
              <div className="flex items-start gap-2">
                <div className="min-w-0 flex-1">
                  <input
                    value={addUrl}
                    onChange={(e) => {
                      setAddUrl(e.target.value);
                      setAddResult(null);
                    }}
                    onKeyDown={(e) => e.key === 'Enter' && void handleAdd()}
                    placeholder={t('docs.addPlaceholder')}
                    disabled={addBusy}
                    className="w-full rounded-xl border-[1.5px] border-dashed border-border-strong bg-transparent px-3.5 py-2 font-mono text-xs placeholder:font-sans placeholder:text-text-muted focus:border-solid focus:border-[#2563eb] focus:outline-none"
                  />
                </div>
                {conns.length > 1 && (
                  <select
                    value={addConnId || conns[0]?.id || ''}
                    onChange={(e) => setAddConnId(e.target.value)}
                    className="flex-none rounded-md border border-border bg-card px-2 py-2 text-xs"
                    data-testid="docs-add-conn-select"
                  >
                    {conns.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.provider_name} · {c.agent_display || (c.agent_address || c.id).split('@')[0]}
                      </option>
                    ))}
                  </select>
                )}
              </div>
              {adopted > 0 && (
                <div className="mt-2.5 rounded-r-lg border-l-[3px] border-[#16a34a] bg-green-50 px-4 py-2 text-xs text-text-muted">
                  {t('docs.adopted', { count: adopted })}
                </div>
              )}
              {unsupported.length > 0 && (
                <div className="mt-2.5 rounded-lg border border-border bg-bg-muted/40 px-3 py-2">
                  <div className="text-[11.5px] text-text-muted">
                    {t('docs.unsupported', { count: unsupported.length })}
                  </div>
                  {unsupported.map((f, i) => (
                    <div key={i} className="flex items-center gap-2 py-1">
                      <span className="min-w-0 flex-1 truncate text-[13px]">{f.title}</span>
                      <span className="flex-none rounded-full bg-bg-muted px-2 py-0.5 text-[11px] text-text-muted">
                        {t(`docs.kind.${f.kind}`, f.kind)}
                      </span>
                    </div>
                  ))}
                </div>
              )}
              {needsEditor.length > 0 && (
                <div className="mt-2.5 rounded-lg border border-border bg-bg-muted/40 px-3 py-2">
                  <div className="mb-1.5 text-[11.5px] text-text-muted">
                    {t('docs.needsEditor', { count: needsEditor.length })}
                  </div>
                  {needsEditor.map((d) => (
                    <div key={d.doc_id} className="flex items-center gap-2 py-1">
                      <a href={d.url} target="_blank" rel="noreferrer" className="min-w-0 flex-1 truncate text-[13px] hover:underline">
                        {d.title || d.doc_id}
                      </a>
                      <span className="flex-none rounded-full bg-amber-50 px-2 py-0.5 text-[11px] text-amber-700">
                        {t('docs.status.comment_only')}
                      </span>
                    </div>
                  ))}
                </div>
              )}
              {addResult && addResult.result !== 'ok' && (
                <div
                  className={`mt-2.5 rounded-r-lg border-l-[3px] px-4 py-3 text-sm ${
                    addResult.result === 'comment_only'
                      ? 'border-amber-500 bg-amber-50'
                      : addResult.result === 'exists'
                        ? 'border-border-strong bg-bg-muted'
                        : 'border-red-500 bg-red-50'
                  }`}
                >
                  <b className="mb-0.5 block text-[13px]">{t(`docs.add.${addResult.result}.title`)}</b>
                  <span className="text-xs text-text-muted">{t(`docs.add.${addResult.result}.detail`)}</span>
                  <div className="mt-2 flex gap-3">
                    {addResult.result === 'not_shared' && (
                      <button onClick={copyAddress} className="text-xs text-[#2563eb] hover:underline">
                        {copied ? t('docs.copied') : t('docs.copyAddress')}
                      </button>
                    )}
                    <button
                      onClick={() => void handleAdd()}
                      className="rounded-md border border-border-strong bg-card px-3 py-1 text-xs"
                    >
                      {t('docs.recheck')}
                    </button>
                  </div>
                </div>
              )}
              <div className="mt-2 flex items-center justify-between font-mono text-[11px] text-text-muted">
                <button
                  onClick={() => window.dispatchEvent(new CustomEvent('jiuwen:navigate-settings', { detail: { module: 'clouddoc' } }))}
                  className="font-sans hover:text-[#2563eb]"
                  data-testid="docs-goto-settings"
                >
                  {t('docs.manageConnInSettings')}
                </button>
                <span>
                  {t('docs.footCount', { count: docs.length })}
                  {refreshedAt ? ` · ${t('docs.refreshedAt', { time: refreshedAt })}` : ''}
                </span>
              </div>
            </div>
          </>
        ) : (
          <div className="flex flex-1 items-center justify-center">
            <div className="max-w-md px-8 text-center">
              <EmptyIllustration />
              <p className="mt-4 text-sm font-medium">{t('docs.noConn')}</p>
              <p className="mt-1.5 text-xs leading-relaxed text-text-muted">{t('docs.notEnabled')}</p>
              <button
                onClick={() => window.dispatchEvent(new CustomEvent('jiuwen:navigate-settings', { detail: { module: 'clouddoc' } }))}
                className="mt-3 rounded-md border border-border px-3 py-1.5 text-xs hover:bg-bg-hover"
                data-testid="docs-goto-settings"
              >
                {t('docs.manageConnInSettings')}
              </button>
            </div>
          </div>
        )}
      </div>

      {usageFor && (
        <div
          data-testid="docs-panel-usage"
          className="fixed inset-0 z-30 flex items-center justify-center bg-black/30"
          onClick={() => setUsageFor(null)}
        >
          <div
            className="max-h-[80vh] w-[min(560px,92vw)] overflow-auto rounded-lg border border-border bg-card p-5 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-3 flex items-start justify-between gap-4">
              <div>
                <h3 className="text-sm font-semibold text-text-strong">{t('docs.usage.title')}</h3>
                <p className="mt-0.5 text-xs text-text-muted">{usageFor.title || usageFor.doc_id}</p>
              </div>
              <button onClick={() => setUsageFor(null)} className="rounded-md px-2 py-1 text-text-muted hover:bg-bg-hover">✕</button>
            </div>
            {usageBusy ? (
              <p className="text-xs text-text-muted">…</p>
            ) : !usage ? (
              <p className="text-xs text-text-muted">{t('docs.usage.unavailable')}</p>
            ) : (
              (() => {
                const g = (usage.granted ?? null) as Record<string, unknown> | null;
                const u = (usage.used ?? {}) as Record<string, unknown>;
                const hints = (usage.hints ?? []) as string[];
                const denials = (u.denials ?? {}) as Record<string, number>;
                const deniedTotal = Object.values(denials).reduce((a, b) => a + b, 0);
                const fmtTs = (v: unknown) =>
                  typeof v === 'number' && v > 0 ? new Date(v * 1000).toLocaleString() : '—';
                const regions = (u.regions_envelope ?? []) as string[];
                const executors = (u.executors ?? []) as string[];
                return (
                  <div className="space-y-3 text-xs">
                    <div className="rounded-md bg-bg-hover px-3 py-2">
                      <p className="font-medium">{t('docs.usage.granted')}</p>
                      <p className="mt-1 text-text-muted">
                        {g
                          ? `${g.mode === 'apply_scoped' ? t('docs.watch.watchApply') : t('docs.watch.watchReply')} · ${t('docs.usage.since')} ${fmtTs(g.issued_at)} · ${
                              g.expires_at == null
                                ? t('docs.usage.permanent')
                                : (g.expired ? t('docs.watch.watchExpired') : `${t('docs.usage.until')} ${fmtTs(g.expires_at)}`)
                            }`
                          : t('docs.watch.watchOff')}
                      </p>
                    </div>
                    <div className="rounded-md bg-bg-hover px-3 py-2">
                      <p className="font-medium">{t('docs.usage.used')}</p>
                      <p className="mt-1 text-text-muted">
                        {t('docs.usage.summaryLine', {
                          dispatches: Number(u.dispatches ?? 0),
                          denied: deniedTotal,
                          writes: Number(u.write_batches ?? 0),
                        })}
                      </p>
                      <p className="mt-0.5 text-text-muted">
                        {t('docs.usage.lastWrite')} {fmtTs(u.last_write_at)}
                        {executors.length > 0 ? ` · ${t('docs.usage.executors')} ${executors.join(', ')}` : ''}
                      </p>
                      {regions.length > 0 && (
                        <p className="mt-0.5 break-all text-text-muted">
                          {t('docs.usage.regions')} {regions.slice(0, 8).join(', ')}{regions.length > 8 ? '…' : ''}
                        </p>
                      )}
                    </div>
                    {hints.length > 0 && (
                      <div className="rounded-md bg-amber-50 px-3 py-2 text-amber-800">
                        {hints.includes('idle_wide_grant') && <p>{t('docs.usage.hintIdle')}</p>}
                        {hints.includes('frequent_denials') && <p>{t('docs.usage.hintFriction')}</p>}
                      </div>
                    )}
                    <div className="flex justify-end gap-2 pt-1">
                      <button
                        data-testid="docs-panel-usage-renew"
                        onClick={() => void renew(usageFor, false)}
                        className="rounded-md border border-border px-3 py-1.5 hover:bg-bg-hover"
                      >
                        {t('docs.usage.renew30')}
                      </button>
                      <button
                        data-testid="docs-panel-usage-permanent"
                        onClick={() => void renew(usageFor, true)}
                        className="rounded-md border border-border px-3 py-1.5 text-text-muted hover:bg-bg-hover"
                      >
                        {t('docs.usage.makePermanent')}
                      </button>
                    </div>
                  </div>
                );
              })()
            )}
          </div>
        </div>
      )}

      {historyFor && (
        <div
          data-testid="docs-panel-history"
          className="fixed inset-0 z-30 flex items-center justify-center bg-black/30"
          onClick={() => setHistoryFor(null)}
        >
          <div
            className="max-h-[80vh] w-[min(720px,92vw)] overflow-auto rounded-lg border border-border bg-card p-5 shadow-xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-3 flex items-start justify-between gap-4">
              <div>
                <h3 className="text-sm font-semibold text-text-strong">{t('docs.history.title')}</h3>
                <p className="mt-0.5 text-xs text-text-muted">{historyFor.title || historyFor.doc_id}</p>
                <p className="mt-1 text-[11px] text-text-muted" data-testid="docs-panel-history-undo-hint">{t('docs.history.undoHint')}</p>
              </div>
              <button
                onClick={() => setHistoryFor(null)}
                className="rounded-md px-2 py-1 text-text-muted hover:bg-bg-hover"
                data-testid="docs-panel-history-close"
              >
                ✕
              </button>
            </div>

            {historyNote && (
              <p data-testid="docs-panel-history-note" className="mb-3 rounded-md bg-bg-hover px-3 py-2 text-xs text-text">
                {historyNote}
              </p>
            )}

            {historyBusy ? (
              <p className="py-6 text-center text-xs text-text-muted">{t('docs.history.loading')}</p>
            ) : receipts.length === 0 ? (
              /* An empty feed is the normal state for a document nobody has assigned
                 work on, so it says that rather than looking like a failure. */
              <p data-testid="docs-panel-history-empty" className="py-6 text-center text-xs text-text-muted">
                {t('docs.history.empty')}
              </p>
            ) : (
              <ul className="flex flex-col gap-2">
                {receipts.map((r) => (
                  <li
                    key={r.receipt_id}
                    data-testid="docs-panel-history-row"
                    data-variant={r.status}
                    className="rounded-md border border-border px-3 py-2"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <span className="text-xs text-text-muted">
                        {new Date((r.ts || 0) * 1000).toLocaleString()}
                        {' · '}
                        <span data-testid="docs-panel-history-status">
                          {t(RECEIPT_STATUS_KEY[r.status] ?? '', { defaultValue: r.status })}
                        </span>
                        {r.highlight ? ` · ${t('docs.history.highlighted')}` : ''}
                      </span>
                      <span className="flex shrink-0 gap-2">
                        {/* Both actions are offered only where they mean something: a
                            batch that never applied has nothing to undo, and one that
                            was not highlighted has nothing to clear. */}
                        {r.status === 'applied' && r.highlight && (
                          <button
                            data-testid="docs-panel-history-unhighlight"
                            disabled={actingOn === r.receipt_id}
                            onClick={() => void actOnReceipt('clouddoc.unhighlight', r.receipt_id)}
                            className="rounded-md border border-border px-2 py-0.5 text-xs hover:bg-bg-hover disabled:opacity-50"
                          >
                            {t('docs.history.unhighlight')}
                          </button>
                        )}
                      </span>
                    </div>
                    {r.status === 'unknown' && (
                      <p
                        data-testid="docs-panel-history-unknown-note"
                        className="mt-1 text-xs text-text-muted"
                      >
                        {r.abort_reason || t('docs.history.unknownNote')}
                      </p>
                    )}
                    {r.op && r.op !== 'edit' && (
                      <p data-testid="docs-panel-history-op" className="mt-1 text-xs text-text">
                        <span className="font-medium">
                          {t(RECEIPT_OP_KEY[r.op] ?? '', { defaultValue: r.op })}
                        </span>
                        {r.subject?.email ? ` · ${r.subject.email}` : ''}
                        {r.subject?.title ? ` · ${r.subject.title}` : ''}
                      </p>
                    )}
                    {(r.edits || []).slice(0, 3).map((e, i) => (
                      <p key={i} className="mt-1 truncate text-xs text-text">
                        <span className="text-text-muted line-through">{e.old || ''}</span>
                        {' → '}
                        <span>{e.new || ''}</span>
                      </p>
                    ))}
                    {(r.edits || []).length > 3 && (
                      <p className="mt-1 text-xs text-text-muted">
                        {t('docs.history.more', { n: (r.edits || []).length - 3 })}
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}

      {removeTarget && (
        <ConfirmDialog
          title={t('docs.remove')}
          message={t('docs.removeConfirm', { title: removeTarget.title })}
          loading={removing}
          onConfirm={() => void handleRemove()}
          onCancel={() => setRemoveTarget(null)}
        />
      )}

      {removeConnTarget && (
        <ConfirmDialog
          title={t('docs.removeConn')}
          message={t('docs.removeConnConfirm', {
            address: removeConnTarget.agent_address,
            count: removeConnTarget.docs_count,
          })}
          loading={removing}
          onConfirm={() => void handleRemoveConnection()}
          onCancel={() => setRemoveConnTarget(null)}
        />
      )}

      {addConnOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/30"
          onClick={resetConnDialog}
          onKeyDown={(e) => e.key === 'Escape' && resetConnDialog()}
          role="dialog"
          aria-modal="true"
          aria-label={t('docs.addConn')}
        >
          <div className="w-[480px] rounded-xl bg-card p-6 shadow-xl" onClick={(e) => e.stopPropagation()}>
            <h3 className="text-lg font-semibold">{t('docs.addConn')}</h3>

            <div className="mt-4">
              <label className="text-xs font-semibold text-text-muted">{t('docs.connProviderLabel')}</label>
              <div className="mt-1.5">
                <SimpleSelect
                  value="google"
                  onChange={() => {}}
                  options={[
                    { value: 'google', label: 'Google Docs' },
                    { value: 'feishu', label: `${t('docs.providerFeishu')}（${t('docs.providerSoon')}）`, disabled: true },
                  ]}
                />
              </div>
            </div>

            <div className="mt-4">
              <label className="block text-xs font-semibold text-text-muted">{t('docs.connKeyLabel')}</label>
              <div className="mt-1.5 inline-flex overflow-hidden rounded-lg border border-border-strong text-xs">
                {(['path', 'upload', 'saved'] as const).map((m) => (
                  <button
                    key={m}
                    onClick={() => {
                      setConnMode(m);
                      setConnError(null);
                      if (m === 'saved') void loadSavedKeys();
                    }}
                    className={`px-3 py-1.5 ${
                      connMode === m ? 'bg-[#eff4fe] font-semibold text-[#2563eb]' : 'bg-card text-text-muted'
                    }`}
                  >
                    {t(`docs.connMode.${m}`)}
                  </button>
                ))}
              </div>
              {connMode === 'saved' ? (
                <div className="mt-2">
                  {savedKeys.length === 0 && (
                    <p className="text-[11.5px] text-text-muted">{t('docs.savedEmpty')}</p>
                  )}
                  {savedKeys.map((k) => (
                    <div
                      key={k.filename}
                      onClick={() => { if (!k.in_use) { setSavedSel(k.filename); setConnError(null); } }}
                      className={`flex items-center gap-2 rounded-lg border px-3 py-2 mb-1.5 ${
                        savedSel === k.filename ? 'border-[#2563eb] bg-[#eff4fe]' : 'border-border'
                      } ${k.in_use ? 'opacity-70' : 'cursor-pointer'}`}
                    >
                      <div className="min-w-0 flex-1">
                        <div className="truncate font-mono text-xs">{k.filename}</div>
                        <div className="truncate text-[11px] text-text-muted">{k.client_email}</div>
                      </div>
                      {k.in_use ? (
                        <span className="flex-none rounded-full bg-green-50 px-2 py-0.5 text-[11px] text-green-700">
                          {t('docs.keyInUse')}
                        </span>
                      ) : (
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            if (keyDeleteArm === k.filename) void deleteSavedKey(k.filename);
                            else setKeyDeleteArm(k.filename);
                          }}
                          className={`flex-none rounded-lg border px-2 py-0.5 text-[11px] ${
                            keyDeleteArm === k.filename
                              ? 'border-red-500 bg-red-50 text-red-600'
                              : 'border-border-strong text-text-muted hover:border-red-400 hover:text-red-500'
                          }`}
                        >
                          {keyDeleteArm === k.filename ? t('docs.keyDeleteConfirm') : t('docs.keyDelete')}
                        </button>
                      )}
                    </div>
                  ))}
                  <p className="mt-1 text-[11px] text-text-muted">{t('docs.keyDeleteHint')}</p>
                </div>
              ) : connMode === 'path' ? (
                <input
                  value={connPath}
                  onChange={(e) => {
                    setConnPath(e.target.value);
                    setConnError(null);
                  }}
                  onKeyDown={(e) => e.key === 'Enter' && void handleAddConnection()}
                  placeholder={t('docs.connPathPlaceholder')}
                  autoFocus
                  className="mt-2 w-full rounded-lg border border-border-strong px-3 py-2 font-mono text-xs focus:border-[#2563eb] focus:outline-none"
                />
              ) : (
                <div className="mt-2">
                  <input
                    id="clouddoc-key-file"
                    type="file"
                    accept=".json,application/json"
                    className="hidden"
                    onChange={(e) => {
                      const f = e.target.files?.[0];
                      if (!f) return;
                      void f.text().then((body) => {
                        setConnJson({ name: f.name, body });
                        setConnError(null);
                      });
                    }}
                  />
                  <label
                    htmlFor="clouddoc-key-file"
                    className="inline-block cursor-pointer rounded-lg border border-border-strong px-3 py-1.5 text-xs hover:border-[#2563eb]"
                  >
                    {connJson ? connJson.name : t('docs.connChooseFile')}
                  </label>
                  <p className="mt-1 text-[11px] text-text-muted">{t('docs.connUploadHint')}</p>
                </div>
              )}
            </div>

            {connError && (
              <div className="mt-3 rounded-r-lg border-l-[3px] border-red-500 bg-red-50 px-3 py-2 text-xs">
                {connError}
              </div>
            )}

            <div className="mt-5 flex justify-end gap-2">
              <button onClick={resetConnDialog} className="rounded-lg border border-border-strong px-4 py-1.5 text-sm">
                {t('docs.cancel')}
              </button>
              <button
                onClick={() => void handleAddConnection()}
                disabled={connBusy || (connMode === 'path' ? !connPath.trim() : connMode === 'saved' ? !savedSel : !connJson)}
                className="rounded-lg bg-[#1f1f23] px-4 py-1.5 text-sm text-white disabled:opacity-50"
              >
                {connBusy ? t('docs.adding') : t('docs.addBtn')}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
