import { useTranslation } from 'react-i18next';
import { Copy, LogOut, UserMinus, UserPlus, X } from 'lucide-react';

import { Button, Select, Tag } from '../../../../channels/web/frontend/src/components/ui';
import type { InviteView, MemberView, Role, WorkspaceView } from '../types';

const ROLES: Role[] = ['owner', 'editor', 'commenter', 'viewer'];

export function MembersPanel({
  workspace,
  members,
  invites,
  meId,
  onSetRole,
  onRemove,
  onLeave,
  onInvite,
  onCopy,
  onRevoke,
}: {
  workspace: WorkspaceView;
  members: MemberView[];
  invites: InviteView[];
  meId: string | null;
  onSetRole: (member: MemberView, role: Role) => void;
  onRemove: (member: MemberView) => void;
  onLeave: () => void;
  onInvite: () => void;
  onCopy: (invite: InviteView) => void;
  onRevoke: (invite: InviteView) => void;
}) {
  const { t } = useTranslation();
  const owner = workspace.role === 'owner';
  const canChange = owner && !workspace.archived;
  const liveInvites = invites.filter((i) => i.state === 'active');

  return (
    <aside className="bb-rail" data-testid="blackboard-members-panel">
      <div className="bb-rail__head">
        <h3 data-testid="blackboard-members-title">{t('blackboard.members.tab')}</h3>
        {canChange ? (
          <Button size="sm" icon={<UserPlus size={14} />} data-testid="blackboard-invite-btn" onClick={onInvite}>
            {t('blackboard.invites.create')}
          </Button>
        ) : null}
      </div>

      <ul className="bb-member-list" data-testid="blackboard-member-list">
        {members.map((m) => {
          const isMe = m.user_id === meId;
          return (
            <li key={m.user_id} className="bb-member" data-testid="blackboard-member-item" data-variant={m.user_id}>
              <div className="bb-member__who">
                <span className="bb-member__name">{m.display_name}</span>
                {isMe ? <span className="bb-muted">({t('blackboard.members.you')})</span> : null}
                {m.disabled ? <Tag variant="warning">{t('blackboard.members.disabled')}</Tag> : null}
              </div>
              <div className="bb-member__controls">
                {/* Your own role is shown, not edited, so the last owner cannot demote themselves by accident. */}
                {canChange && !isMe ? (
                  <Select
                    className="bb-member__role"
                    data-testid="blackboard-member-role-select"
                    data-variant={m.user_id}
                    aria-label={t('blackboard.members.role', { name: m.display_name })}
                    value={m.role}
                    options={ROLES.map((role) => ({ value: role, label: t(`blackboard.roles.${role}`) }))}
                    onChange={(value) => onSetRole(m, value as Role)}
                  />
                ) : (
                  <Tag variant={m.role === 'owner' ? 'info' : 'neutral'} data-testid="blackboard-member-role" data-variant={m.role}>
                    {t(`blackboard.roles.${m.role}`)}
                  </Tag>
                )}
                {canChange && !isMe ? (
                  <Button
                    size="sm"
                    variant="quiet"
                    icon={<UserMinus size={16} />}
                    aria-label={t('blackboard.members.remove')}
                    title={t('blackboard.members.remove')}
                    data-testid="blackboard-member-remove-btn"
                    data-variant={m.user_id}
                    onClick={() => onRemove(m)}
                  />
                ) : null}
              </div>
            </li>
          );
        })}
      </ul>

      {owner ? (
        <div className="bb-rail__section" data-testid="blackboard-invites">
          <h4>{t('blackboard.invites.title')}</h4>
          {liveInvites.length === 0 ? (
            <p className="bb-muted" data-testid="blackboard-invites-empty">
              {t('blackboard.invites.empty')}
            </p>
          ) : (
            <ul className="bb-invite-list" data-testid="blackboard-invite-list">
              {liveInvites.map((invite) => (
                <li key={invite.code} className="bb-invite" data-testid="blackboard-invite-item" data-variant={invite.code}>
                  <p className="bb-invite__meta">
                    {[
                      t(`blackboard.roles.${invite.role}`),
                      invite.max_uses === null
                        ? t('blackboard.invites.metaUses', { uses: invite.uses })
                        : t('blackboard.invites.metaUsesOf', { uses: invite.uses, max: invite.max_uses }),
                      invite.expires_at === null
                        ? t('blackboard.invites.metaNeverExpires')
                        : t('blackboard.invites.metaExpires', {
                            date: new Date(invite.expires_at).toLocaleString(undefined, {
                              dateStyle: 'short',
                              timeStyle: 'short',
                            }),
                          }),
                    ].join(' · ')}
                  </p>
                  <div className="bb-invite__actions">
                    <Button
                      size="sm"
                      variant="quiet"
                      icon={<Copy size={14} />}
                      data-testid="blackboard-invite-copy-btn"
                      data-variant={invite.code}
                      onClick={() => onCopy(invite)}
                    >
                      {t('blackboard.invites.copy')}
                    </Button>
                    <Button
                      size="sm"
                      variant="quiet"
                      icon={<X size={14} />}
                      data-testid="blackboard-invite-revoke-btn"
                      data-variant={invite.code}
                      onClick={() => onRevoke(invite)}
                    >
                      {t('blackboard.invites.revoke')}
                    </Button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>
      ) : null}

      <div className="bb-rail__footer">
        <Button size="sm" variant="quiet" icon={<LogOut size={14} />} data-testid="blackboard-leave-btn" onClick={onLeave}>
          {t('blackboard.workspace.leave')}
        </Button>
      </div>
    </aside>
  );
}
