/**
 * Receipt rows as the panel RPCs return them, and the two label maps the Docs
 * panel and the document workbench share. One place, so a status or act added
 * to the ledger is labelled the same everywhere it is shown.
 */
import type { ToolExecution } from '../../types/message';

export type ReceiptOp = 'edit' | 'create' | 'share' | 'trash' | 'restore' | 'unshare';

export type ReceiptRow = {
  receipt_id: string;
  ts: number;
  doc_id: string;
  status: string;
  abort_reason?: string;
  unverified_detail?: string;
  reverted_by?: string;
  highlight?: boolean;
  executor?: string;
  source?: string;
  edits?: { old?: string; new?: string; region?: string; anchor?: string }[];
  op?: ReceiptOp;
  subject?: { title?: string; email?: string; role?: string };
};

export const RECEIPT_STATUS_KEY: Record<string, string> = {
  pending: 'docs.history.statusPending',
  applied: 'docs.history.statusApplied',
  applied_unverified: 'docs.history.statusAppliedUnverified',
  aborted: 'docs.history.statusAborted',
  reverted: 'docs.history.statusReverted',
  unknown: 'docs.history.statusUnknown',
};

export const RECEIPT_OP_KEY: Record<string, string> = {
  create: 'docs.history.opCreate',
  share: 'docs.history.opShare',
  trash: 'docs.history.opTrash',
  restore: 'docs.history.opRestore',
  unshare: 'docs.history.opUnshare',
};

/** The region a receipt wrote, for the workbench's locate: a cell range, a
 *  slide address or, for a text edit, nothing (text is located by content). */
export function receiptRegions(r: ReceiptRow): string[] {
  return (r.edits || []).map((e) => e.region || '').filter(Boolean);
}

/** The platform URL fragment that lands a browser on the receipt's first
 *  region (`#gid=…&range=…`, `#slide=id.…`), recorded by the writer; empty for
 *  a text edit or a platform without anchors. */
export function receiptAnchor(r: ReceiptRow): string {
  return (r.edits || []).map((e) => e.anchor || '').find(Boolean) ?? '';
}

/**
 * Receipt ids the session's own tool calls produced, newest last. The tool
 * result is the ledger's word (`receipt_id` in the JSON the tool returned); a
 * model that merely mentions a number is not a source.
 */
export function receiptsFromExecutions(
  executions: Iterable<ToolExecution> | undefined,
): { receiptId: string; docId: string; toolName: string; at: string }[] {
  const out: { receiptId: string; docId: string; toolName: string; at: string }[] = [];
  if (!executions) return out;
  for (const exec of executions) {
    const name = exec.toolCall?.name ?? '';
    if (!name.startsWith('clouddoc_') || !exec.result?.result) continue;
    let parsed: unknown;
    try {
      parsed = JSON.parse(exec.result.result);
    } catch {
      continue;
    }
    if (!parsed || typeof parsed !== 'object') continue;
    const rid = (parsed as { receipt_id?: unknown }).receipt_id;
    const args = exec.toolCall?.arguments as { doc_id?: unknown } | undefined;
    const docId = (parsed as { doc_id?: unknown }).doc_id ?? args?.doc_id;
    if (typeof rid === 'string' && rid && typeof docId === 'string') {
      out.push({ receiptId: rid, docId, toolName: name, at: exec.updatedAt || exec.startedAt });
    }
  }
  return out;
}
