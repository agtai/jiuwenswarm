/**
 * The chat-side notice a personal cloud-doc connection delivers (release §13,
 * matrix S.3/S.4): someone @-mentioned the person or assigned them a comment.
 * Document name, the quoted text, the comment, and one entry point -- "handle it"
 * opens the workbench with the comment drafted into the composer. Nothing here
 * writes to the document.
 */
import { useTranslation } from 'react-i18next';
import { AtSign, FileText } from 'lucide-react';
import { handleNotice, type CloudDocNotice } from '../../features/clouddoc/notices';

export function CloudDocNoticeCard({ notice }: { notice: CloudDocNotice }) {
  const { t } = useTranslation();
  const title = notice.title || notice.doc_id;
  const text = notice.text || notice.comment || '';
  return (
    <div className="flex justify-center my-2 animate-fade-in" data-testid="chat-clouddoc-notice">
      <div className="w-[85%] max-w-[44rem] rounded-lg border border-border bg-bg-hover/60 px-3 py-2 text-xs leading-5">
        <div className="flex items-center gap-1.5 text-text-muted">
          <AtSign size={13} />
          <span>{notice.kind === 'assigned' ? t('docs.notice.assigned') : t('docs.notice.mentioned')}</span>
          <span className="inline-flex items-center gap-1 font-medium text-text" data-testid="chat-clouddoc-notice-title">
            <FileText size={12} />
            {title}
          </span>
          {notice.author && <span>· {notice.author}</span>}
        </div>
        {notice.quoted_text && (
          <blockquote className="mt-1 border-l-2 border-border pl-2 text-text-muted" data-testid="chat-clouddoc-notice-quote">
            {notice.quoted_text}
          </blockquote>
        )}
        {text && <p className="mt-1 whitespace-pre-wrap break-words text-text" data-testid="chat-clouddoc-notice-text">{text}</p>}
        <div className="mt-1.5 flex items-center gap-3">
          <button
            type="button"
            className="rounded-md border border-border bg-card px-2.5 py-0.5 text-xs hover:bg-bg-hover"
            onClick={() => handleNotice(notice, t)}
            data-testid="chat-clouddoc-notice-handle"
          >
            {t('docs.notice.handle')}
          </button>
          {notice.url && notice.url.startsWith('http') && (
            <a href={notice.url} target="_blank" rel="noreferrer" className="text-text-link hover:underline">
              {t('docs.workbench.openExternal')}
            </a>
          )}
          <span className="text-text-muted">{t('docs.notice.noAutoReply')}</span>
        </div>
      </div>
    </div>
  );
}
