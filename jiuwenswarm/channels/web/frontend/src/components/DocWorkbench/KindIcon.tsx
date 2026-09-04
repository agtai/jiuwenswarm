/** Stroke icons per document kind, tinted by platform; no emoji. */
export function KindIcon({ kind, provider, size = 14 }: { kind: string; provider: string; size?: number }) {
  const tint = provider === 'feishu' ? '#3370ff' : kind === 'spreadsheet' ? '#0f9d58' : kind === 'presentation' ? '#f4b400' : kind === 'markdown' ? '#52525b' : '#4285f4';
  if (kind === 'markdown') {
    return (
      <svg viewBox="0 0 24 24" width={size} height={size} aria-hidden="true">
        <rect x="3" y="5" width="18" height="14" rx="2" fill={tint} />
        <path d="M6 15V9l3 3 3-3v6M15 9v6M13 13l2 2 2-2" stroke="#fff" strokeWidth="1.4" fill="none" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    );
  }
  const inner = kind === 'spreadsheet'
    ? <path d="M9 11h7v7H9zM9 14.5h7M12.5 11v7" stroke="#fff" strokeWidth="1.2" fill="none" />
    : kind === 'presentation'
      ? <rect x="9" y="12" width="7" height="5" stroke="#fff" strokeWidth="1.2" fill="none" />
      : <path d="M9 12h6M9 15h6M9 18h4" stroke="#fff" strokeWidth="1.5" />;
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} aria-hidden="true">
      <path d="M6 2h9l5 5v15H6z" fill={tint} />
      <path d="M15 2v5h5" fill="#fff" fillOpacity="0.5" />
      {inner}
    </svg>
  );
}
