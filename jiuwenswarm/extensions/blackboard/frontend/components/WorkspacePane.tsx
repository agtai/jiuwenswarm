import { useTranslation } from 'react-i18next';
import { Archive, ArchiveRestore, FileText, Pencil, Trash2 } from 'lucide-react';

import { Button, Tag } from '../../../../channels/web/frontend/src/components/ui';
import type { WorkspaceView } from '../types';

export function WorkspacePane({
  workspace,
  onRename,
  onArchive,
  onUnarchive,
  onDelete,
}: {
  workspace: WorkspaceView;
  onRename: () => void;
  onArchive: () => void;
  onUnarchive: () => void;
  onDelete: () => void;
}) {
  const { t } = useTranslation();
  const owner = workspace.role === 'owner';
  return (
    <section className="bb-workspace" data-testid="blackboard-workspace">
      <header className="bb-workspace__head">
        <div className="bb-workspace__heading">
          <h2 data-testid="blackboard-workspace-title">{workspace.title}</h2>
          <p className="bb-muted">
            <span data-testid="blackboard-workspace-handle">{t('blackboard.workspace.handle', { name: workspace.name })}</span>
            <Tag variant={owner ? 'info' : 'neutral'} data-testid="blackboard-workspace-role" data-variant={workspace.role}>
              {t(`blackboard.roles.${workspace.role}`)}
            </Tag>
          </p>
        </div>
        {owner ? (
          <div className="bb-workspace__actions">
            <Button size="sm" variant="quiet" icon={<Pencil size={14} />} data-testid="blackboard-workspace-rename-btn" onClick={onRename}>
              {t('blackboard.workspace.rename')}
            </Button>
            {workspace.archived ? (
              <>
                <Button
                  size="sm"
                  variant="quiet"
                  icon={<ArchiveRestore size={14} />}
                  data-testid="blackboard-workspace-unarchive-btn"
                  onClick={onUnarchive}
                >
                  {t('blackboard.workspace.unarchive')}
                </Button>
                <Button size="sm" variant="danger" icon={<Trash2 size={14} />} data-testid="blackboard-workspace-delete-btn" onClick={onDelete}>
                  {t('blackboard.workspace.delete')}
                </Button>
              </>
            ) : (
              <Button size="sm" variant="quiet" icon={<Archive size={14} />} data-testid="blackboard-workspace-archive-btn" onClick={onArchive}>
                {t('blackboard.workspace.archive')}
              </Button>
            )}
          </div>
        ) : null}
      </header>
      {workspace.archived ? (
        <p className="bb-notice" data-testid="blackboard-workspace-archived-notice">
          {t('blackboard.workspace.archivedNotice')}
        </p>
      ) : null}
      <div className="bb-empty" data-testid="blackboard-documents-empty">
        <FileText aria-hidden="true" />
        <p>{t('blackboard.workspace.documentsEmpty')}</p>
      </div>
    </section>
  );
}
