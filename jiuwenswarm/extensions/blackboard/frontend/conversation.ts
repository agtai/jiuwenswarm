// Comments and the chat without React: mentions, the host's coded notices, thread order.
import type { Mention, ThreadView } from './types';

export const AGENT_HANDLE = 'jiuwen';

// The same rule as the host (common/mentions.py): @jiuwen as a word, not inside an address.
const AGENT = /(^|[^\w@])@jiuwen\b/i;

export function namesAgent(body: string): boolean {
  return AGENT.test(body);
}

function escape(text: string): string {
  return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

// The mentions a body makes: the agent, and members written as @Name.
export function mentionsIn(body: string, members: Array<{ user_id: string; display_name: string }>): Mention[] {
  const out: Mention[] = [];
  if (namesAgent(body)) out.push({ kind: 'agent' });
  for (const member of members) {
    if (!member.display_name) continue;
    const pattern = new RegExp(`(^|[^\\w@])@${escape(member.display_name)}(?![\\w])`, 'i');
    if (pattern.test(body)) out.push({ kind: 'user', id: member.user_id });
  }
  return out;
}

// The handle being typed before the caret, for the mention list: "@ali" gives {start, query: "ali"}.
export function mentionAt(text: string, caret: number): { start: number; query: string } | null {
  const before = text.slice(0, caret);
  const match = /(^|\s)@([^\s@]{0,40})$/.exec(before);
  if (!match) return null;
  return { start: caret - match[2].length - 1, query: match[2] };
}

// A notice or summary the host wrote: JSON with a code and its parameters.
export function coded(body: string): { code: string; params: Record<string, string> } | null {
  try {
    const value = JSON.parse(body);
    if (!value || typeof value.code !== 'string') return null;
    const { code, ...params } = value;
    return { code, params: Object.fromEntries(Object.entries(params).map(([k, v]) => [k, String(v ?? '')])) };
  } catch {
    return null;
  }
}

// Open threads as the document reads (those without a place last), then resolved ones, newest first.
export function sortThreads(threads: ThreadView[]): ThreadView[] {
  const open = threads.filter((t) => !t.resolved_at);
  const resolved = threads.filter((t) => t.resolved_at);
  open.sort((a, b) => (a.position ?? Number.MAX_SAFE_INTEGER) - (b.position ?? Number.MAX_SAFE_INTEGER) || a.created_at.localeCompare(b.created_at));
  resolved.sort((a, b) => (b.resolved_at ?? '').localeCompare(a.resolved_at ?? ''));
  return [...open, ...resolved];
}

// Yjs relative positions travel as base64.
export function toBase64(bytes: Uint8Array): string {
  let text = '';
  for (const byte of bytes) text += String.fromCharCode(byte);
  return btoa(text);
}

export function fromBase64(text: string): Uint8Array {
  const raw = atob(text);
  const out = new Uint8Array(raw.length);
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
  return out;
}

export function normalizeText(text: string): string {
  return text.split(/\s+/).filter(Boolean).join(' ');
}

export const CARD_GAP = 8;
const CARD_HEIGHT = 72;

// Where the margin's cards go: each level with its passage when there is room, otherwise pushed down
// below the card before it. The active card stays level with its passage and the cards above it
// move up to make room. `wanted` is in document order.
export function placeCards(
  wanted: Array<{ id: string; top: number }>,
  heights: ReadonlyMap<string, number>,
  active: string | null,
): Map<string, number> {
  const height = (id: string) => heights.get(id) ?? CARD_HEIGHT;
  const tops = new Map<string, number>();
  const pivot = active ? Math.max(0, wanted.findIndex((w) => w.id === active)) : 0;
  let below = -Infinity;
  for (let i = pivot; i < wanted.length; i++) {
    const top = Math.max(wanted[i].top, below);
    tops.set(wanted[i].id, top);
    below = top + height(wanted[i].id) + CARD_GAP;
  }
  let above = pivot < wanted.length ? tops.get(wanted[pivot].id)! - CARD_GAP : Infinity;
  for (let i = pivot - 1; i >= 0; i--) {
    const top = Math.min(wanted[i].top, above - height(wanted[i].id));
    tops.set(wanted[i].id, top);
    above = top - CARD_GAP;
  }
  return tops;
}
