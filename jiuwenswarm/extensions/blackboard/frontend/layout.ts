// Sizes and hidden parts of the page (the left sidebar, the panels on the right), per browser.
// Which panels are open is the controller's; this is only how much room each gets.
import { useSyncExternalStore } from 'react';

import type { RailTab } from './controller';

export interface Layout {
  sidebarWidth: number;
  sidebarHidden: boolean;
  dockWidth: number;
  dockHidden: boolean;
  // How the open panels share the height, and the ones folded to their header.
  weights: Partial<Record<RailTab, number>>;
  collapsed: RailTab[];
  // The chat box over the page: the agent sessions in it, the one shown, and whether it is folded.
  chats: string[];
  chat: string | null;
  chatMinimized: boolean;
  chatWidth: number;
  chatHeight: number;
}

export const LIMITS = { sidebar: [180, 480], dock: [260, 760], chatWidth: [300, 960], chatHeight: [240, 1400] } as const;
const DEFAULT_LAYOUT: Layout = {
  sidebarWidth: 260,
  sidebarHidden: false,
  dockWidth: 340,
  dockHidden: false,
  weights: {},
  collapsed: [],
  chats: [],
  chat: null,
  chatMinimized: false,
  chatWidth: 380,
  chatHeight: 520,
};
const KEY = 'blackboard.layout';

export const clamp = (value: number, [low, high]: readonly [number, number]) => Math.round(Math.max(low, Math.min(high, value)));

function load(): Layout {
  try {
    const saved = JSON.parse(window.localStorage.getItem(KEY) ?? 'null');
    if (!saved || typeof saved !== 'object') return DEFAULT_LAYOUT;
    return {
      sidebarWidth: clamp(Number(saved.sidebarWidth) || DEFAULT_LAYOUT.sidebarWidth, LIMITS.sidebar),
      sidebarHidden: Boolean(saved.sidebarHidden),
      dockWidth: clamp(Number(saved.dockWidth) || DEFAULT_LAYOUT.dockWidth, LIMITS.dock),
      dockHidden: Boolean(saved.dockHidden),
      weights: saved.weights && typeof saved.weights === 'object' ? saved.weights : {},
      collapsed: Array.isArray(saved.collapsed) ? saved.collapsed : [],
      chats: Array.isArray(saved.chats) ? saved.chats.filter((id: unknown) => typeof id === 'string') : [],
      chat: typeof saved.chat === 'string' ? saved.chat : null,
      chatMinimized: Boolean(saved.chatMinimized),
      chatWidth: clamp(Number(saved.chatWidth) || DEFAULT_LAYOUT.chatWidth, LIMITS.chatWidth),
      chatHeight: clamp(Number(saved.chatHeight) || DEFAULT_LAYOUT.chatHeight, LIMITS.chatHeight),
    };
  } catch {
    return DEFAULT_LAYOUT;
  }
}

let current: Layout | null = null;
const listeners = new Set<() => void>();

function get(): Layout {
  current ??= load();
  return current;
}

export function updateLayout(change: Partial<Layout> | ((layout: Layout) => Partial<Layout>)): void {
  const base = get();
  current = { ...base, ...(typeof change === 'function' ? change(base) : change) };
  try {
    window.localStorage.setItem(KEY, JSON.stringify(current));
  } catch {
    // Kept for this page only then.
  }
  listeners.forEach((listener) => listener());
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useLayout(): Layout {
  return useSyncExternalStore(subscribe, get);
}

// Open a session in the chat box (adding it as a tab) and show the box.
export function openChat(sessionId: string): void {
  updateLayout((l) => ({ chats: l.chats.includes(sessionId) ? l.chats : [...l.chats, sessionId], chat: sessionId, chatMinimized: false }));
}

export function closeChat(sessionId: string): void {
  updateLayout((l) => {
    const chats = l.chats.filter((id) => id !== sessionId);
    return { chats, chat: l.chat === sessionId ? (chats[chats.length - 1] ?? null) : l.chat };
  });
}
