/**
 * 文档工作台状态：打开的文档标签页、当前标签、右栏与底部聊天条的显隐。
 *
 * 标签页是应用级的，不按 session 隔离——同一份文档不论从哪个会话打开都是同一个标签；
 * 底部聊天条永远是当前 session 的流，由 App 渲染时注入。显隐偏好落 localStorage。
 */
import { create } from 'zustand';

export type WorkbenchDocKind = 'document' | 'spreadsheet' | 'presentation' | 'markdown' | string;

export interface WorkbenchTab {
  docId: string;
  title: string;
  kind: WorkbenchDocKind;
  url: string;
  provider: string;
  providerName?: string;
  /** 本标签不在前台时新到的回执数；切到它时清零。 */
  unread: number;
  /** 本标签已见过的回执 id，用于判断「新到」。 */
  seenReceiptIds: string[];
}

export type RailTab = 'receipts' | 'history' | 'status';

interface DocWorkbenchState {
  open: boolean;
  tabs: WorkbenchTab[];
  activeDocId: string | null;
  railTab: RailTab;
  railVisible: boolean;
  chatVisible: boolean;
  /** 按平台记住的「总是在新标签打开」。 */
  alwaysNewTab: Record<string, boolean>;
  /** 主界面 iframe 的重载计数（按文档），新回执到达时 +1。 */
  reloadNonce: Record<string, number>;
  /** 定位请求：切到该文档并把回执的区域交给主界面。 */
  locate: { docId: string; receiptId: string; anchor: string; nonce: number } | null;

  openDoc: (meta: Omit<WorkbenchTab, 'unread' | 'seenReceiptIds'>) => void;
  activate: (docId: string) => void;
  closeTab: (docId: string) => void;
  exit: () => void;
  /** 从任务主界面回到文档编辑（仍有打开的标签时）。 */
  reopen: () => void;
  setRailTab: (tab: RailTab) => void;
  toggleRail: () => void;
  toggleChat: () => void;
  setAlwaysNewTab: (provider: string, value: boolean) => void;
  /** 记录一份文档最新的回执 id 列表；返回本次新增的数量。 */
  noteReceipts: (docId: string, receiptIds: string[]) => number;
  requestLocate: (docId: string, receiptId: string, anchor?: string) => void;
}

const PREFS_KEY = 'jiuwenswarm.docWorkbench.prefs.v1';

function loadPrefs(): { railVisible: boolean; chatVisible: boolean; alwaysNewTab: Record<string, boolean> } {
  try {
    const raw = localStorage.getItem(PREFS_KEY);
    if (raw) {
      const p = JSON.parse(raw) as Partial<{ railVisible: boolean; chatVisible: boolean; alwaysNewTab: Record<string, boolean> }>;
      return {
        railVisible: p.railVisible ?? true,
        chatVisible: p.chatVisible ?? true,
        alwaysNewTab: p.alwaysNewTab ?? {},
      };
    }
  } catch {
    /* no storage: defaults */
  }
  return { railVisible: true, chatVisible: true, alwaysNewTab: {} };
}

function savePrefs(s: Pick<DocWorkbenchState, 'railVisible' | 'chatVisible' | 'alwaysNewTab'>): void {
  try {
    localStorage.setItem(PREFS_KEY, JSON.stringify({
      railVisible: s.railVisible, chatVisible: s.chatVisible, alwaysNewTab: s.alwaysNewTab,
    }));
  } catch {
    /* ignore */
  }
}

export const useDocWorkbenchStore = create<DocWorkbenchState>((set, get) => ({
  open: false,
  tabs: [],
  activeDocId: null,
  railTab: 'receipts',
  reloadNonce: {},
  locate: null,
  ...loadPrefs(),

  openDoc: (meta) => set((s) => {
    const existing = s.tabs.find((t) => t.docId === meta.docId);
    const tabs = existing
      ? s.tabs.map((t) => (t.docId === meta.docId ? { ...t, ...meta, unread: 0 } : t))
      : [...s.tabs, { ...meta, unread: 0, seenReceiptIds: [] }];
    return { open: true, tabs, activeDocId: meta.docId };
  }),
  activate: (docId) => set((s) => ({
    activeDocId: docId,
    tabs: s.tabs.map((t) => (t.docId === docId ? { ...t, unread: 0 } : t)),
  })),
  closeTab: (docId) => set((s) => {
    const tabs = s.tabs.filter((t) => t.docId !== docId);
    const activeDocId = s.activeDocId === docId ? (tabs[tabs.length - 1]?.docId ?? null) : s.activeDocId;
    return { tabs, activeDocId, open: tabs.length > 0 ? s.open : false };
  }),
  exit: () => set({ open: false }),
  reopen: () => set((s) => (s.tabs.length > 0 ? { open: true } : {})),
  setRailTab: (railTab) => set({ railTab }),
  toggleRail: () => set((s) => {
    const next = { railVisible: !s.railVisible };
    savePrefs({ ...s, ...next });
    return next;
  }),
  toggleChat: () => set((s) => {
    const next = { chatVisible: !s.chatVisible };
    savePrefs({ ...s, ...next });
    return next;
  }),
  setAlwaysNewTab: (provider, value) => set((s) => {
    const alwaysNewTab = { ...s.alwaysNewTab, [provider]: value };
    savePrefs({ ...s, alwaysNewTab });
    return { alwaysNewTab };
  }),
  noteReceipts: (docId, receiptIds) => {
    const s = get();
    const tab = s.tabs.find((t) => t.docId === docId);
    if (!tab) return 0;
    const seen = new Set(tab.seenReceiptIds);
    const fresh = receiptIds.filter((id) => !seen.has(id));
    // The first listing seeds what "seen" means; only later arrivals count as new.
    const isFirst = tab.seenReceiptIds.length === 0;
    const added = isFirst ? 0 : fresh.length;
    if (fresh.length === 0) return 0;
    set({
      tabs: s.tabs.map((t) => (t.docId === docId
        ? { ...t, seenReceiptIds: [...t.seenReceiptIds, ...fresh], unread: t.docId === s.activeDocId ? 0 : t.unread + added }
        : t)),
      reloadNonce: added > 0 ? { ...s.reloadNonce, [docId]: (s.reloadNonce[docId] ?? 0) + 1 } : s.reloadNonce,
    });
    return added;
  },
  requestLocate: (docId, receiptId, anchor = '') => set((s) => ({
    activeDocId: docId,
    locate: { docId, receiptId, anchor, nonce: (s.locate?.nonce ?? 0) + 1 },
  })),
}));
