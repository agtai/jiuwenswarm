// Same rule as client/invite_link.py: <host url>/blackboard/join/<20 base32 chars>.
const CODE = /^[a-z2-7]{20}$/;
const MARKER = '/blackboard/join/';

export interface ParsedInvite {
  base: string;
  code: string;
}

export function parseInviteLink(text: string): ParsedInvite | null {
  const trimmed = text.trim();
  if (!trimmed) return null;
  let url: URL;
  try {
    url = new URL(trimmed);
  } catch {
    return null;
  }
  if (url.protocol !== 'http:' && url.protocol !== 'https:') return null;
  const index = url.pathname.indexOf(MARKER);
  if (index < 0) return null;
  const code = url.pathname.slice(index + MARKER.length).replace(/^\/+|\/+$/g, '');
  if (!CODE.test(code)) return null;
  return { base: `${url.protocol}//${url.host}${url.pathname.slice(0, index)}`.replace(/\/+$/, ''), code };
}

// A workspace short name: 3-40 of a-z, 0-9 and '-', not starting or ending with '-', no '--'.
export function isValidWorkspaceName(name: string): boolean {
  return /^[a-z0-9](?:[a-z0-9-]{1,38}[a-z0-9])$/.test(name) && !name.includes('--');
}

// Suggest a short name from a title: "Launch plan Q4" -> "launch-plan-q4".
export function suggestWorkspaceName(title: string): string {
  return title
    .toLowerCase()
    .normalize('NFKD')
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/-{2,}/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 40)
    .replace(/-+$/g, '');
}
