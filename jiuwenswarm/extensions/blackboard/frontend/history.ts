// Helpers for the History tab that need no React: versions grouped by day, and merging a version
// that just arrived into the list.
import type { VersionView } from './types';

// The local calendar day of an ISO time, as YYYY-MM-DD, so days group by the reader's clock.
export function localDay(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return '';
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;
}

// Newest first in, newest day first out, each day's versions still newest first.
export function groupByDay(versions: VersionView[]): Array<{ day: string; versions: VersionView[] }> {
  const groups: Array<{ day: string; versions: VersionView[] }> = [];
  for (const version of versions) {
    const day = localDay(version.created_at);
    const last = groups[groups.length - 1];
    if (last && last.day === day) last.versions.push(version);
    else groups.push({ day, versions: [version] });
  }
  return groups;
}

// A version pushed by the host joins the top of the list once.
export function withVersion(versions: VersionView[], version: VersionView): VersionView[] {
  return versions.some((v) => v.id === version.id) ? versions : [version, ...versions];
}
