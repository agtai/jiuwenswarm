/**
 * The bottom chat strip: the current session's own stream, reduced to the last
 * agent message, its receipt chip and the composer. History lives in the rail.
 */
import { useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Minus, MessageSquare, ChevronUp } from 'lucide-react';
import { useChatStore } from '../../stores/chatStore';
import { InputArea } from '../ChatPanel/InputArea';
import beeAvatar from '../../assets/bee-static.png';
import type { ComponentProps } from 'react';
import { activeToolDocId, receiptsFromExecutions } from '../../features/clouddoc/receipts';

export type ComposerProps = ComponentProps<typeof InputArea>;

export function ChatStrip({ composer, visible, docTitle, titleOf, onHide, onShow, unreadReceipts, onLocate, onHistory }: {
  composer: ComposerProps;
  visible: boolean;
  /** 聚焦标签页的文档名，作为回落值。 */
  docTitle?: string;
  /** doc_id -> 标题，用来给"正在编辑"标签取模型实际在动的那篇。 */
  titleOf?: (docId: string) => string;
  onHide: () => void;
  onShow: () => void;
  unreadReceipts: number;
  onLocate: (docId: string, receiptId: string) => void;
  onHistory: () => void;
}) {
  const { t } = useTranslation();
  const sid = useChatStore((s) => s.activeSessionId) ?? '';
  const messages = useChatStore((s) => s.runtimes[sid]?.messages);
  const executions = useChatStore((s) => s.runtimes[sid]?.toolExecutions);
  const last = useMemo(() => {
    const list = messages ?? [];
    for (let i = list.length - 1; i >= 0; i--) if (list[i].role === 'assistant' && list[i].content) return list[i];
    return null;
  }, [messages]);
  // The tag names what the model is working on, not what the person is looking
  // at: the two differ whenever a turn reaches a document in another tab. The
  // focused tab is only the fallback before any tool has run.
  const workingTitle = useMemo(() => {
    const docId = activeToolDocId(executions ? executions.values() : undefined);
    const named = docId && titleOf ? titleOf(docId) : '';
    return named || docTitle || '';
  }, [executions, titleOf, docTitle]);
  const lastReceipt = useMemo(() => {
    const all = receiptsFromExecutions(executions ? executions.values() : undefined);
    return all.length ? all[all.length - 1] : null;
  }, [executions]);

  if (!visible) {
    return (
      <button type="button" className="doc-workbench__chat-pill" onClick={onShow} data-testid="doc-workbench-chat-pill">
        <MessageSquare size={14} /> {t('docs.workbench.chat')}
        {unreadReceipts > 0 && <span className="doc-workbench__tab-dot" style={{ background: 'var(--color-conversation-unread)' }} />}
        {unreadReceipts > 0 && <span className="text-text-muted">{t('docs.workbench.newReceipts', { n: unreadReceipts })}</span>}
        <ChevronUp size={14} />
      </button>
    );
  }
  return (
    <div className="doc-workbench__chat" data-testid="doc-workbench-chat">
      <div className="doc-workbench__chat-last">
        <img src={beeAvatar} className="doc-workbench__chat-avatar" alt="jiuwen" />
        {workingTitle && (
          <span className="doc-workbench__chat-doc" title={workingTitle} data-testid="doc-workbench-chat-doc">
            {t('docs.workbench.editingDoc')}{workingTitle}
          </span>
        )}
        <span className="doc-workbench__chat-last-text" data-testid="doc-workbench-chat-last">{last?.content ?? t('docs.workbench.noReplyYet')}</span>
        {lastReceipt && (
          <span className="inline-flex items-center gap-2" data-testid="doc-workbench-chat-receipt">
            <span className="font-mono text-[11px] text-text-muted">{t('docs.workbench.receipt')} {lastReceipt.receiptId.slice(0, 8)}</span>
            <a className="text-xs text-text-link hover:underline" onClick={() => onLocate(lastReceipt.docId, lastReceipt.receiptId)}>{t('docs.workbench.locate')}</a>
          </span>
        )}
        <a className="text-xs text-text-link hover:underline" onClick={onHistory}>{t('docs.workbench.history')}</a>
        <div className="h-4 w-px bg-border" />
        <button type="button" className="doc-workbench__icon-btn" style={{ width: 24, height: 24 }} onClick={onHide} title={t('docs.workbench.hideChat')} data-testid="doc-workbench-chat-hide"><Minus size={16} /></button>
      </div>
      <InputArea {...composer} />
    </div>
  );
}
