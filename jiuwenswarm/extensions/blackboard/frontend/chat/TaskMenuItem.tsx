import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import clsx from 'clsx';
import { ChevronRight, Loader2 } from 'lucide-react';

import type { ApplicationPluginTaskMenuItemProps } from '../../../../channels/web/frontend/src/applicationPlugins/types';
import { PickerPanel } from '../../../../channels/web/frontend/src/components/ChatPanel/PickerPanel';
import { Switch } from '../../../../channels/web/frontend/src/components/Switch';
import { BlackboardIcon } from '../BlackboardIcon';
import { errorText } from '../controller';
import type { SessionAttachmentView } from '../types';
import { openBlackboard, rpc } from '../useController';
import { isAttached, sessionAttachments, toggleAttachment, workspaceChoices, type WorkspaceChoice } from './sessionLink';

const ROW_HEIGHT = 44;

// "Blackboard workspace" in the chat's + menu: choose the workspaces this session's agent works on.
export function BlackboardTaskMenuItem({
  sessionId,
  ensureSession,
  direction,
  teamMode,
  panelOpen,
  onPanelOpenChange,
  closeMenu,
}: ApplicationPluginTaskMenuItemProps) {
  const { t } = useTranslation();
  const anchorRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!panelOpen) return;
    const onPointerDown = (event: PointerEvent) => {
      if (!anchorRef.current?.contains(event.target as Node)) onPanelOpenChange(false);
    };
    document.addEventListener('pointerdown', onPointerDown);
    return () => document.removeEventListener('pointerdown', onPointerDown);
  }, [panelOpen, onPanelOpenChange]);

  // Blackboard's tools reach single-agent sessions only.
  if (teamMode) return null;
  return (
    <div ref={anchorRef} className="chat-attach-menu-item-anchor">
      <button
        type="button"
        className={clsx('chat-mode-select__option', panelOpen && 'chat-mode-select__option--panel-open')}
        role="menuitem"
        aria-haspopup="menu"
        aria-expanded={panelOpen}
        data-testid="blackboard-chat-menu-item"
        onClick={() => onPanelOpenChange(!panelOpen)}
      >
        <span className="chat-mode-select__option-main">
          <span className="chat-mode-select__icon chat-mode-select__icon--asset" aria-hidden="true">
            <BlackboardIcon width={16} height={16} />
          </span>
          <span className="chat-mode-select__label">{t('blackboard.chat.menuItem')}</span>
        </span>
        <ChevronRight className="chat-mode-select__chevron" size={16} aria-hidden="true" />
      </button>
      {panelOpen ? (
        <WorkspacePanel
          sessionId={sessionId}
          ensureSession={ensureSession}
          direction={direction}
          onOpenBlackboard={() => {
            closeMenu();
            openBlackboard();
          }}
        />
      ) : null}
    </div>
  );
}

function WorkspacePanel({
  sessionId,
  ensureSession,
  direction,
  onOpenBlackboard,
}: {
  sessionId: string | null;
  ensureSession: (initialTitle?: string) => Promise<string | null>;
  direction: 'up' | 'down';
  onOpenBlackboard: () => void;
}) {
  const { t } = useTranslation();
  const panelRef = useRef<HTMLDivElement>(null);
  const [choices, setChoices] = useState<WorkspaceChoice[] | null>(null);
  const [current, setCurrent] = useState<SessionAttachmentView[]>([]);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    Promise.all([workspaceChoices(rpc), sessionId ? sessionAttachments(rpc, sessionId) : Promise.resolve([])]).then(
      ([loaded, attachment]) => {
        if (!alive) return;
        setChoices(loaded);
        setCurrent(attachment);
      },
      (err) => {
        if (!alive) return;
        setChoices([]);
        setError(errorText(err));
      },
    );
    return () => {
      alive = false;
    };
  }, [sessionId]);

  const toggle = async (choice: WorkspaceChoice) => {
    setBusy(choice.workspaceId);
    setError(null);
    try {
      const sid = sessionId ?? (await ensureSession(choice.title));
      if (!sid) return;
      setCurrent(await toggleAttachment(rpc, sid, choice, current));
    } catch (err) {
      setError(errorText(err));
    } finally {
      setBusy(null);
    }
  };

  const hosts = new Set((choices ?? []).map((c) => c.host));
  return (
    <PickerPanel
      panelRef={panelRef}
      className="chat-extension-picker"
      direction={direction}
      testId="blackboard-chat-workspace-panel"
      rowHeight={ROW_HEIGHT}
      itemCount={choices?.length ?? 0}
      search={
        <p className="bb-chat-panel__hint" data-testid="blackboard-chat-workspace-hint">
          {t('blackboard.chat.hint')}
        </p>
      }
      footer={{ label: t('blackboard.chat.openBlackboard'), onClick: onOpenBlackboard }}
    >
      {choices === null ? (
        <div className="chat-skill-select__state" data-testid="blackboard-chat-workspace-state" data-variant="loading">
          {t('blackboard.chat.loading')}
        </div>
      ) : choices.length === 0 && !error ? (
        <div className="chat-skill-select__state" data-testid="blackboard-chat-workspace-state" data-variant="empty">
          {t('blackboard.chat.empty')}
        </div>
      ) : null}
      {error ? (
        <div className="chat-skill-select__state bb-chat-panel__error" data-testid="blackboard-chat-workspace-state" data-variant="error">
          {error}
        </div>
      ) : null}
      {(choices ?? []).map((choice) => {
        const on = isAttached(current, choice);
        return (
          <div
            key={`${choice.host}/${choice.workspaceId}`}
            className="chat-skill-select__item chat-extension-picker__item"
            data-testid="blackboard-chat-workspace-item"
            data-variant={choice.title}
            aria-current={on || undefined}
          >
            <span className="bb-chat-choice__icon" aria-hidden="true">
              <BlackboardIcon width={16} height={16} />
            </span>
            <div className="chat-skill-select__item-main">
              <div className="chat-skill-select__item-name" data-testid="blackboard-chat-workspace-title">
                {choice.title}
              </div>
              {hosts.size > 1 ? <div className="bb-chat-choice__host">{choice.hostName}</div> : null}
            </div>
            {busy === choice.workspaceId ? (
              <Loader2 className="chat-extension-picker__spinner" size={16} />
            ) : (
              <Switch
                checked={on}
                disabled={busy !== null}
                title={on ? t('blackboard.chat.detach') : t('blackboard.chat.attach')}
                onChange={() => void toggle(choice)}
              />
            )}
          </div>
        );
      })}
    </PickerPanel>
  );
}
