import { useTranslation } from 'react-i18next';
import { Link2, Plus, Settings2 } from 'lucide-react';

import { Button, Select } from '../../../../channels/web/frontend/src/components/ui';
import type { BlackboardState } from '../controller';
import type { WorkspaceView } from '../types';

export function Sidebar({
  state,
  onSelectHost,
  onSelectWorkspace,
  onJoin,
  onNewWorkspace,
  onSettings,
}: {
  state: BlackboardState;
  onSelectHost: (hostId: string) => void;
  onSelectWorkspace: (workspaceId: string) => void;
  onJoin: () => void;
  onNewWorkspace: () => void;
  onSettings: () => void;
}) {
  const { t } = useTranslation();
  const host = state.hosts.find((h) => h.id === state.hostId) ?? null;
  const active = state.workspaces.filter((w) => !w.archived);
  const archived = state.workspaces.filter((w) => w.archived);

  return (
    <aside className="bb-sidebar" data-testid="blackboard-sidebar">
      <div className="bb-sidebar__host">
        <div className="bb-sidebar__host-row">
          <Select
            className="bb-sidebar__host-select"
            data-testid="blackboard-host-select"
            aria-label={t('blackboard.host.label')}
            value={state.hostId ?? ''}
            disabled={state.hosts.length === 0}
            options={state.hosts.map((h) => ({
              value: h.id,
              label: h.is_self ? `${h.name} (${t('blackboard.host.self')})` : h.name,
            }))}
            onChange={onSelectHost}
          />
          <Button
            variant="quiet"
            size="sm"
            icon={<Settings2 size={16} />}
            aria-label={t('blackboard.host.settings')}
            title={t('blackboard.host.settings')}
            data-testid="blackboard-settings-btn"
            onClick={onSettings}
          />
        </div>
        {host ? (
          <p className="bb-sidebar__host-status" data-testid="blackboard-host-status" data-variant={host.status}>
            <span className={`bb-status-dot bb-status-dot--${host.status}`} aria-hidden="true" />
            {t(`blackboard.host.status.${host.status}`)}
          </p>
        ) : null}
        <Button size="sm" icon={<Link2 size={14} />} data-testid="blackboard-join-btn" onClick={onJoin}>
          {t('blackboard.host.join')}
        </Button>
      </div>

      <div className="bb-sidebar__section">
        <div className="bb-sidebar__section-head">
          <h3 data-testid="blackboard-workspaces-title">{t('blackboard.workspaces.title')}</h3>
          <Button
            variant="quiet"
            size="sm"
            icon={<Plus size={16} />}
            aria-label={t('blackboard.workspaces.new')}
            title={t('blackboard.workspaces.new')}
            disabled={!host}
            data-testid="blackboard-new-workspace-btn"
            onClick={onNewWorkspace}
          />
        </div>
        {host && active.length === 0 && archived.length === 0 ? (
          <p className="bb-muted" data-testid="blackboard-workspaces-empty">
            {t('blackboard.workspaces.empty')}
          </p>
        ) : null}
        <WorkspaceList items={active} selected={state.workspaceId} onSelect={onSelectWorkspace} />
        {archived.length > 0 ? (
          <>
            <h4 className="bb-sidebar__subhead" data-testid="blackboard-workspaces-archived-title">
              {t('blackboard.workspaces.archived')}
            </h4>
            <WorkspaceList items={archived} selected={state.workspaceId} onSelect={onSelectWorkspace} />
          </>
        ) : null}
      </div>
    </aside>
  );
}

function WorkspaceList({
  items,
  selected,
  onSelect,
}: {
  items: WorkspaceView[];
  selected: string | null;
  onSelect: (workspaceId: string) => void;
}) {
  const { t } = useTranslation();
  if (items.length === 0) return null;
  return (
    <ul className="bb-workspace-list" data-testid="blackboard-workspace-list">
      {items.map((w) => (
        <li key={w.id}>
          <button
            type="button"
            className={`bb-workspace-item${w.id === selected ? ' is-selected' : ''}`}
            aria-pressed={w.id === selected}
            data-testid="blackboard-workspace-item"
            data-variant={w.name}
            onClick={() => onSelect(w.id)}
          >
            <span className="bb-workspace-item__title">{w.title}</span>
            <span className="bb-workspace-item__role">{t(`blackboard.roles.${w.role}`)}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}
