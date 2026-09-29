// The open document's versions, newest first and grouped by day: when, why, and who. A version
// opens in place of the editor; editors can save a named version of the document as it is now.
import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import type { TFunction } from 'i18next';
import { Bookmark, Bot, FileInput, FilePlus2, Pencil, RotateCcw, Save } from 'lucide-react';

import { Button, Input } from '../../../../channels/web/frontend/src/components/ui';
import { groupByDay, localDay } from '../history';
import type { DocView, VersionReason, VersionView } from '../types';

const REASON_ICONS: Record<VersionReason, typeof Bot> = {
  created: FilePlus2,
  agent_turn: Bot,
  idle: Pencil,
  import: FileInput,
  restore: RotateCcw,
  manual: Bookmark,
};

export function versionAuthors(t: TFunction, version: VersionView): string {
  return version.authors.map((a) => (a.kind === 'agent' ? t('blackboard.agents.agentOf', { name: a.name }) : a.name)).join(', ');
}

export function versionTime(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? '' : date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function dayLabel(t: TFunction, day: string): string {
  const today = localDay(new Date().toISOString());
  const yesterday = localDay(new Date(Date.now() - 86400000).toISOString());
  if (day === today) return t('blackboard.history.today');
  if (day === yesterday) return t('blackboard.history.yesterday');
  const date = new Date(`${day}T00:00:00`);
  return Number.isNaN(date.getTime()) ? day : date.toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric', year: 'numeric' });
}

export function HistoryPanel({
  doc,
  versions,
  hasMore,
  openVersion,
  canSave,
  onOpen,
  onSave,
  onMore,
}: {
  doc: DocView | null;
  versions: VersionView[];
  hasMore: boolean;
  openVersion: string | null;
  canSave: boolean;
  onOpen: (versionId: string | null) => void;
  onSave: (label: string) => Promise<void>;
  onMore: () => void;
}) {
  const { t } = useTranslation();
  const [naming, setNaming] = useState(false);
  const [label, setLabel] = useState('');
  const [busy, setBusy] = useState(false);

  if (!doc) {
    return (
      <div className="bb-rail__panel bb-history" data-testid="blackboard-history-panel">
        <p className="bb-muted">{t('blackboard.history.noDoc')}</p>
      </div>
    );
  }

  const save = async () => {
    setBusy(true);
    try {
      await onSave(label.trim());
      setNaming(false);
      setLabel('');
    } catch {
      // The page showed the error; the form stays open.
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="bb-rail__panel bb-history" data-testid="blackboard-history-panel">
      <p className="bb-muted">{t('blackboard.history.intro')}</p>
      {canSave ? (
        naming ? (
          <div className="bb-history__save">
            <Input
              value={label}
              maxLength={200}
              autoFocus
              placeholder={t('blackboard.history.labelPlaceholder')}
              data-testid="blackboard-history-label-input"
              onChange={setLabel}
            />
            <div className="bb-history__save-actions">
              <Button size="sm" variant="primary" loading={busy} data-testid="blackboard-history-save-confirm-btn" onClick={() => void save()}>
                {t('blackboard.history.save')}
              </Button>
              <Button size="sm" variant="quiet" data-testid="blackboard-history-save-cancel-btn" onClick={() => setNaming(false)}>
                {t('common.cancel')}
              </Button>
            </div>
          </div>
        ) : (
          <Button size="sm" icon={<Save size={14} />} data-testid="blackboard-history-save-btn" onClick={() => setNaming(true)}>
            {t('blackboard.history.saveVersion')}
          </Button>
        )
      ) : null}
      {versions.length === 0 ? (
        <p className="bb-muted" data-testid="blackboard-history-empty">
          {t('blackboard.history.empty')}
        </p>
      ) : null}
      {groupByDay(versions).map((group) => (
        <section key={group.day} className="bb-history__day">
          <h4>{dayLabel(t, group.day)}</h4>
          <ul className="bb-history__list">
            {group.versions.map((version) => {
              const Icon = REASON_ICONS[version.reason] ?? Pencil;
              const selected = version.id === openVersion;
              return (
                <li key={version.id}>
                  <button
                    type="button"
                    className={`bb-history__item${selected ? ' is-selected' : ''}`}
                    aria-pressed={selected}
                    data-testid="blackboard-version-item"
                    data-variant={version.id}
                    data-reason={version.reason}
                    onClick={() => onOpen(selected ? null : version.id)}
                  >
                    <span className="bb-history__line">
                      <Icon size={13} aria-hidden="true" />
                      <strong>{versionTime(version.created_at)}</strong>
                      <span className="bb-muted">{t(`blackboard.history.reason.${version.reason}`)}</span>
                    </span>
                    {version.label ? <span className="bb-history__label">{version.label}</span> : null}
                    {version.authors.length ? (
                      <span className="bb-history__authors" data-testid="blackboard-version-authors">
                        {versionAuthors(t, version)}
                      </span>
                    ) : null}
                    {version.mandate_instruction ? <span className="bb-muted bb-history__why">{version.mandate_instruction}</span> : null}
                  </button>
                </li>
              );
            })}
          </ul>
        </section>
      ))}
      {hasMore ? (
        <Button size="sm" variant="quiet" data-testid="blackboard-history-more-btn" onClick={onMore}>
          {t('blackboard.history.older')}
        </Button>
      ) : null}
    </div>
  );
}
