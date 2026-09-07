/**
 * Personal-identity notices (release §13, matrix S.3/S.4).
 *
 * A personal connection's watcher never answers in the document; it tells the
 * person here. The gateway pushes `clouddoc.notice`, the chat shows one system
 * message per notice (its content is the JSON behind NOTICE_PREFIX, rendered as a
 * card), and "handle it" opens the workbench with the comment in the composer.
 */
import { requestOpenDoc } from './openDocSignal';
import { webRequest } from '../../services/webClient';

export interface CloudDocNotice {
  notice_id?: string;
  key?: string;
  doc_id: string;
  title?: string;
  url?: string;
  connection_id?: string;
  comment_id: string;
  reply_id?: string | null;
  kind?: 'mention' | 'assigned' | string;
  author?: string;
  quoted_text?: string;
  comment?: string;
  text?: string;
  created_time?: string;
  ts?: number;
  read?: boolean;
}

export const NOTICE_PREFIX = 'clouddoc.notice:';
export const NOTICE_EVENT = 'jiuwen:clouddoc-notice';

export function noticeMessageContent(n: CloudDocNotice): string {
  return NOTICE_PREFIX + JSON.stringify(n);
}

export function parseNoticeContent(content: string): CloudDocNotice | null {
  if (!content.startsWith(NOTICE_PREFIX)) return null;
  try {
    const v = JSON.parse(content.slice(NOTICE_PREFIX.length)) as CloudDocNotice;
    return v && typeof v.doc_id === 'string' && typeof v.comment_id === 'string' ? v : null;
  } catch {
    return null;
  }
}

/**
 * The composer text "handle it" leaves in the person's hands. It names the
 * document and the comment id (the id the tools need), quotes what was quoted,
 * and repeats the comment -- and stops there: the person decides what to ask.
 */
export function noticePrompt(n: CloudDocNotice, t: (k: string, o?: Record<string, unknown>) => string): string {
  const title = n.title || n.doc_id;
  const lines = [t('docs.notice.promptHead', { title, comment_id: n.comment_id })];
  if (n.quoted_text) lines.push(t('docs.notice.promptQuote', { quote: n.quoted_text }));
  lines.push(t('docs.notice.promptComment', { author: n.author || '', text: n.text || n.comment || '' }));
  lines.push(t('docs.notice.promptTail'));
  return lines.join('\n');
}

/** Open the workbench on the notice's document, with the comment in the composer, and mark it read. */
export function handleNotice(n: CloudDocNotice, t: (k: string, o?: Record<string, unknown>) => string): void {
  if (n.notice_id) void webRequest('clouddoc.notice_ack', { notice_id: n.notice_id }).catch(() => undefined);
  requestOpenDoc(n.doc_id, { prompt: noticePrompt(n, t) });
}
