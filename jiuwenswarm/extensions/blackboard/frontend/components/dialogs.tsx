import { useEffect, useId, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Copy, Link2 } from 'lucide-react';

import { FormDialog } from '../../../../channels/web/frontend/src/components/form';
import { Button, Input, Select, Switch } from '../../../../channels/web/frontend/src/components/ui';
import { describeError } from '../errors';
import { isValidWorkspaceName, parseInviteLink, suggestWorkspaceName } from '../inviteLink';
import type { HostHealth, HostStatus, InviteRole, InviteView } from '../types';
import { Field } from './Field';
import { AccessKey, HostPeople, type AccessActions } from './AccessSettings';
import { BotMode, ConnectedAccounts, HostBots, type ImActions } from './ImSettings';

// Runs `action`, keeps the dialog open with the error if it throws.
export function useSubmit(onDone: () => void) {
  const { t } = useTranslation();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = async (action: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await action();
      onDone();
    } catch (err) {
      setError(describeError(t, err));
    } finally {
      setBusy(false);
    }
  };
  return { busy, error, setError, run };
}

export function Status({ error }: { error: string | null }) {
  return error ? (
    <p className="bb-dialog-error" role="alert" data-testid="blackboard-dialog-error">
      {error}
    </p>
  ) : null;
}

export function JoinDialog({
  open,
  onJoin,
  onClose,
}: {
  open: boolean;
  onJoin: (url: string, displayName: string) => Promise<unknown>;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const linkId = useId();
  const nameId = useId();
  const [link, setLink] = useState('');
  const [name, setName] = useState('');
  const { busy, error, setError, run } = useSubmit(onClose);
  useEffect(() => {
    if (open) {
      setLink('');
      setError(null);
    }
  }, [open]);
  const parsed = parseInviteLink(link);
  const linkError = link.trim() && !parsed ? t('blackboard.join.invalidLink') : null;
  return (
    <FormDialog
      open={open}
      title={t('blackboard.join.title')}
      description={t('blackboard.join.description')}
      confirmLabel={t('blackboard.join.submit')}
      cancelLabel={t('common.cancel')}
      confirmLoading={busy}
      submitting={busy}
      confirmDisabled={!parsed || !name.trim()}
      status={<Status error={error} />}
      testIdPrefix="blackboard-join-dialog"
      onConfirm={() => void run(() => onJoin(link.trim(), name.trim()))}
      onCancel={onClose}
    >
      <Field label={t('blackboard.join.link')} htmlFor={linkId} error={linkError}>
        <Input
          id={linkId}
          value={link}
          placeholder={t('blackboard.join.linkPlaceholder')}
          invalid={Boolean(linkError)}
          data-testid="blackboard-join-link-input"
          onChange={setLink}
        />
      </Field>
      <Field label={t('blackboard.join.name')} htmlFor={nameId} hint={t('blackboard.join.nameHint')}>
        <Input id={nameId} value={name} maxLength={60} data-testid="blackboard-join-name-input" onChange={setName} />
      </Field>
    </FormDialog>
  );
}

export function NewWorkspaceDialog({
  open,
  onCreate,
  onClose,
}: {
  open: boolean;
  onCreate: (name: string, title: string) => Promise<unknown>;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const titleId = useId();
  const nameId = useId();
  const [title, setTitle] = useState('');
  const [name, setName] = useState('');
  const [nameTouched, setNameTouched] = useState(false);
  const { busy, error, setError, run } = useSubmit(onClose);
  useEffect(() => {
    if (open) {
      setTitle('');
      setName('');
      setNameTouched(false);
      setError(null);
    }
  }, [open]);
  const shownName = nameTouched ? name : suggestWorkspaceName(title);
  const nameError = shownName && !isValidWorkspaceName(shownName) ? t('blackboard.newWorkspace.invalidName') : null;
  return (
    <FormDialog
      open={open}
      title={t('blackboard.newWorkspace.title')}
      confirmLabel={t('blackboard.newWorkspace.submit')}
      cancelLabel={t('common.cancel')}
      confirmLoading={busy}
      submitting={busy}
      confirmDisabled={!title.trim() || !isValidWorkspaceName(shownName)}
      status={<Status error={error} />}
      testIdPrefix="blackboard-new-workspace-dialog"
      onConfirm={() => void run(() => onCreate(shownName, title.trim()))}
      onCancel={onClose}
    >
      <Field label={t('blackboard.newWorkspace.titleLabel')} htmlFor={titleId}>
        <Input id={titleId} value={title} maxLength={120} data-testid="blackboard-new-workspace-title-input" onChange={setTitle} />
      </Field>
      <Field
        label={t('blackboard.newWorkspace.nameLabel')}
        htmlFor={nameId}
        hint={t('blackboard.newWorkspace.nameHint')}
        error={nameError}
      >
        <Input
          id={nameId}
          value={shownName}
          maxLength={40}
          prefix="@bb:"
          invalid={Boolean(nameError)}
          data-testid="blackboard-new-workspace-name-input"
          onChange={(value) => {
            setNameTouched(true);
            setName(value.toLowerCase());
          }}
        />
      </Field>
    </FormDialog>
  );
}

export function RenameDialog({
  open,
  current,
  heading,
  testId = 'blackboard-rename',
  onRename,
  onClose,
}: {
  open: boolean;
  current: string;
  // Defaults to renaming the workspace.
  heading?: string;
  // Prefix of the dialog's test ids.
  testId?: string;
  onRename: (title: string) => Promise<unknown>;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const inputId = useId();
  const [title, setTitle] = useState(current);
  const { busy, error, setError, run } = useSubmit(onClose);
  useEffect(() => {
    if (open) {
      setTitle(current);
      setError(null);
    }
  }, [open, current]);
  return (
    <FormDialog
      open={open}
      title={heading ?? t('blackboard.rename.title')}
      confirmLabel={t('blackboard.rename.submit')}
      cancelLabel={t('common.cancel')}
      confirmLoading={busy}
      submitting={busy}
      confirmDisabled={!title.trim() || title.trim() === current}
      status={<Status error={error} />}
      testIdPrefix={`${testId}-dialog`}
      onConfirm={() => void run(() => onRename(title.trim()))}
      onCancel={onClose}
    >
      <Field label={t('blackboard.newWorkspace.titleLabel')} htmlFor={inputId}>
        <Input id={inputId} value={title} maxLength={120} data-testid={`${testId}-input`} onChange={setTitle} />
      </Field>
    </FormDialog>
  );
}

export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel,
  danger,
  onConfirm,
  onClose,
  testId,
}: {
  open: boolean;
  title: string;
  message: string;
  confirmLabel: string;
  danger?: boolean;
  onConfirm: () => Promise<unknown>;
  onClose: () => void;
  testId: string;
}) {
  const { t } = useTranslation();
  const { busy, error, setError, run } = useSubmit(onClose);
  useEffect(() => {
    if (open) setError(null);
  }, [open]);
  return (
    <FormDialog
      open={open}
      title={title}
      confirmLabel={confirmLabel}
      cancelLabel={t('common.cancel')}
      confirmLoading={busy}
      submitting={busy}
      status={<Status error={error} />}
      testIdPrefix={testId}
      testVariant={danger ? 'danger' : undefined}
      onConfirm={() => void run(onConfirm)}
      onCancel={onClose}
    >
      <p className="bb-dialog-text">{message}</p>
    </FormDialog>
  );
}

// Discord's choices: expiry in minutes or 'never', uses as a count or 'none' (no limit).
const EXPIRY_OPTIONS = ['30', '60', '360', '720', '1440', '10080', 'never'] as const;
const USES_OPTIONS = ['none', '1', '5', '10', '25', '50', '100'] as const;
const DEFAULT_EXPIRY = '10080';
const DEFAULT_USES = 'none';

// Laid out like Slack's and Discord's invite dialogs: the role first, a link that is
// one click away, and the link's limits in a sentence with the settings behind "Change".
export function InviteDialog({
  open,
  workspaceTitle,
  reachable,
  onCreate,
  onCopy,
  onClose,
}: {
  open: boolean;
  workspaceTitle: string;
  reachable: boolean;
  onCreate: (role: InviteRole, expiresInMinutes: number | null, maxUses: number | null) => Promise<InviteView>;
  onCopy: (invite: InviteView) => void;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const [role, setRole] = useState<InviteRole>('editor');
  const [expiry, setExpiry] = useState<string>(DEFAULT_EXPIRY);
  const [uses, setUses] = useState<string>(DEFAULT_USES);
  const [showLimits, setShowLimits] = useState(false);
  const [link, setLink] = useState<InviteView | null>(null);
  const { busy, error, setError, run } = useSubmit(() => undefined);
  useEffect(() => {
    if (open) {
      setLink(null);
      setShowLimits(false);
      setError(null);
    }
  }, [open]);
  // A link carries its role and limits, so changing either means a new link next time.
  const change = (apply: () => void) => {
    apply();
    setLink(null);
  };
  const createAndCopy = () =>
    run(async () => {
      const invite = await onCreate(
        role,
        expiry === 'never' ? null : Number(expiry),
        uses === 'none' ? null : Number(uses),
      );
      setLink(invite);
      onCopy(invite);
    });
  return (
    <FormDialog
      open={open}
      title={t('blackboard.invites.dialogTitle', { title: workspaceTitle })}
      confirmLabel={t('blackboard.invites.done')}
      cancelLabel={t('common.cancel')}
      dialogClassName="bb-dialog--close-only"
      status={<Status error={error} />}
      testIdPrefix="blackboard-invite-dialog"
      onConfirm={onClose}
      onCancel={onClose}
    >
      {!reachable ? (
        <p className="bb-notice" data-testid="blackboard-invite-not-reachable">
          {t('blackboard.invites.notReachable')}
        </p>
      ) : null}
      <div className="bb-invite-role">
        <span className="bb-field__label">{t('blackboard.invites.joinAs')}</span>
        <Select
          data-testid="blackboard-invite-role-select"
          value={role}
          options={(['editor', 'commenter', 'viewer'] as InviteRole[]).map((r) => ({
            value: r,
            label: t(`blackboard.roles.${r}`),
          }))}
          onChange={(value) => change(() => setRole(value as InviteRole))}
        />
      </div>
      <section className="bb-invite-link" data-testid="blackboard-invite-link">
        <span className="bb-field__label">{t('blackboard.invites.byLink')}</span>
        {link ? (
          <div className="bb-inline">
            <Input value={link.url} readOnly data-testid="blackboard-invite-link-output" />
            <Button icon={<Copy size={16} />} data-testid="blackboard-invite-copy-link-btn" onClick={() => onCopy(link)}>
              {t('blackboard.invites.copy')}
            </Button>
          </div>
        ) : (
          <Button
            variant="primary"
            icon={<Link2 size={16} />}
            loading={busy}
            data-testid="blackboard-invite-create-link-btn"
            onClick={() => void createAndCopy()}
          >
            {t('blackboard.invites.createLink')}
          </Button>
        )}
        <p className="bb-field__hint" data-testid="blackboard-invite-limits">
          {t('blackboard.invites.linkSummary', {
            expiry: t(`blackboard.invites.expiryOptions.${expiry}`),
            uses: t(`blackboard.invites.usesOptions.${uses}`),
          })}{' '}
          <button
            type="button"
            className="bb-link-button"
            aria-expanded={showLimits}
            data-testid="blackboard-invite-limits-btn"
            onClick={() => setShowLimits(!showLimits)}
          >
            {t('blackboard.invites.change')}
          </button>
        </p>
        {showLimits ? (
          <div className="bb-invite-limits">
            <Field label={t('blackboard.invites.expires')}>
              <Select
                data-testid="blackboard-invite-expiry-select"
                value={expiry}
                options={EXPIRY_OPTIONS.map((value) => ({ value, label: t(`blackboard.invites.expiryOptions.${value}`) }))}
                onChange={(value) => change(() => setExpiry(value))}
              />
            </Field>
            <Field label={t('blackboard.invites.maxUses')}>
              <Select
                data-testid="blackboard-invite-uses-select"
                value={uses}
                options={USES_OPTIONS.map((value) => ({ value, label: t(`blackboard.invites.usesOptions.${value}`) }))}
                onChange={(value) => change(() => setUses(value))}
              />
            </Field>
          </div>
        ) : null}
      </section>
    </FormDialog>
  );
}

const LOOPBACK = new Set(['127.0.0.1', 'localhost', '::1']);

export function SettingsDialog({
  open,
  hostName,
  hostUrl,
  displayName,
  hostStatus,
  isOperator,
  profile,
  im,
  access,
  onHealth,
  onSaveName,
  onApplyHosting,
  onClose,
}: {
  open: boolean;
  hostName: string | null;
  // The current host's address, for the plain-HTTP warning.
  hostUrl: string | null;
  displayName: string;
  hostStatus: HostStatus | null;
  // The person runs the current host: they make its shared bots and manage its people.
  isOperator: boolean;
  // Changes when the profile reloads, so connected accounts load again.
  profile: unknown;
  im: ImActions;
  access: AccessActions;
  onHealth: () => Promise<HostHealth>;
  onSaveName: (name: string) => Promise<unknown>;
  onApplyHosting: (settings: Record<string, unknown>) => Promise<unknown>;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const nameId = useId();
  const boardNameId = useId();
  const portId = useId();
  const urlId = useId();
  const originsId = useId();
  const retentionId = useId();
  const [name, setName] = useState(displayName);
  const [boardName, setBoardName] = useState('');
  const [enabled, setEnabled] = useState(false);
  const [openToOthers, setOpenToOthers] = useState(false);
  const [port, setPort] = useState('19011');
  const [publicUrl, setPublicUrl] = useState('');
  const [origins, setOrigins] = useState('');
  const [retention, setRetention] = useState('0');
  const nameSubmit = useSubmit(() => undefined);
  const hostSubmit = useSubmit(() => undefined);
  const [health, setHealth] = useState<HostHealth | null>(null);

  // The profile loads after hosting starts, so the name follows it while the dialog is open.
  useEffect(() => {
    if (open) setName(displayName);
  }, [open, displayName]);

  useEffect(() => {
    if (!open) return;
    const settings = hostStatus?.settings;
    setEnabled(Boolean(settings?.enabled));
    setBoardName(String(settings?.name ?? ''));
    setOpenToOthers(settings ? !LOOPBACK.has(String(settings.bind)) : false);
    setPort(String(settings?.port ?? 19011));
    setPublicUrl(String(settings?.public_url ?? ''));
    setOrigins(Array.isArray(settings?.allowed_origins) ? (settings.allowed_origins as string[]).join(', ') : '');
    setRetention(String(settings?.version_retention_days ?? 0));
    nameSubmit.setError(null);
    hostSubmit.setError(null);
  }, [open]);

  const applyHosting = () =>
    hostSubmit.run(() =>
      onApplyHosting({
        enabled,
        name: boardName.trim(),
        bind: openToOthers ? '0.0.0.0' : '127.0.0.1',
        port: Number(port),
        public_url: publicUrl.trim(),
        allowed_origins: origins
          .split(',')
          .map((o) => o.trim())
          .filter(Boolean),
        version_retention_days: Number(retention) || 0,
      }),
    );

  const running = Boolean(hostStatus?.running);
  const address = hostStatus?.base_url ?? '';
  useEffect(() => {
    if (!open || !running) return setHealth(null);
    onHealth().then(setHealth, () => setHealth(null));
  }, [open, running]);
  const docs = health?.docservice;
  return (
    <FormDialog
      open={open}
      title={t('blackboard.settings.title')}
      confirmLabel={t('common.close')}
      cancelLabel={t('common.cancel')}
      dialogClassName="bb-dialog--close-only"
      testIdPrefix="blackboard-settings-dialog"
      onConfirm={onClose}
      onCancel={onClose}
    >
      {hostName ? (
        <section className="bb-settings-section" data-testid="blackboard-settings-profile">
          <Field
            label={t('blackboard.settings.profile', { host: hostName })}
            htmlFor={nameId}
            error={nameSubmit.error}
          >
            <div className="bb-inline">
              <Input id={nameId} value={name} maxLength={60} data-testid="blackboard-settings-name-input" onChange={setName} />
              <Button
                loading={nameSubmit.busy}
                disabled={!name.trim() || name.trim() === displayName}
                data-testid="blackboard-settings-name-save-btn"
                onClick={() => void nameSubmit.run(() => onSaveName(name.trim()))}
              >
                {t('blackboard.settings.saveName')}
              </Button>
            </div>
          </Field>
        </section>
      ) : null}

      <section className="bb-settings-section" data-testid="blackboard-settings-hosting">
        <div className="bb-settings-row">
          <div>
            <h4>{t('blackboard.settings.hosting')}</h4>
            <p className="bb-muted">{t('blackboard.settings.hostingHint')}</p>
          </div>
          <Switch
            checked={enabled}
            aria-label={t('blackboard.settings.hosting')}
            data-testid="blackboard-settings-hosting-switch"
            onChange={setEnabled}
          />
        </div>
        {enabled ? (
          <>
            <Field
              label={t('blackboard.settings.boardName')}
              htmlFor={boardNameId}
              hint={t('blackboard.settings.boardNameHint')}
            >
              <Input
                id={boardNameId}
                value={boardName}
                maxLength={60}
                placeholder={hostStatus?.name || t('blackboard.settings.boardNamePlaceholder')}
                data-testid="blackboard-settings-board-name-input"
                onChange={setBoardName}
              />
            </Field>
            <Field label={t('blackboard.settings.who')}>
              <Select
                data-testid="blackboard-settings-bind-select"
                value={openToOthers ? 'all' : 'local'}
                options={[
                  { value: 'local', label: t('blackboard.settings.whoLocal') },
                  { value: 'all', label: t('blackboard.settings.whoAll') },
                ]}
                onChange={(value) => setOpenToOthers(value === 'all')}
              />
            </Field>
            <Field label={t('blackboard.settings.port')} htmlFor={portId}>
              <Input id={portId} value={port} inputMode="numeric" data-testid="blackboard-settings-port-input" onChange={setPort} />
            </Field>
            {openToOthers ? (
              <Field label={t('blackboard.settings.publicUrl')} htmlFor={urlId} hint={t('blackboard.settings.publicUrlHint')}>
                <Input
                  id={urlId}
                  value={publicUrl}
                  placeholder="http://192.168.1.20:19011"
                  data-testid="blackboard-settings-public-url-input"
                  onChange={setPublicUrl}
                />
              </Field>
            ) : null}
            {openToOthers ? (
              <Field label={t('blackboard.settings.allowedOrigins')} htmlFor={originsId} hint={t('blackboard.settings.allowedOriginsHint')}>
                <Input
                  id={originsId}
                  value={origins}
                  placeholder="https://jiuwen.example.com"
                  data-testid="blackboard-settings-origins-input"
                  onChange={setOrigins}
                />
              </Field>
            ) : null}
            <Field label={t('blackboard.settings.retention')} htmlFor={retentionId} hint={t('blackboard.settings.retentionHint')}>
              <Input id={retentionId} value={retention} inputMode="numeric" data-testid="blackboard-settings-retention-input" onChange={setRetention} />
            </Field>
          </>
        ) : null}
        {hostStatus?.env_overrides?.length ? (
          <p className="bb-notice" data-testid="blackboard-settings-env-overrides">
            {t('blackboard.settings.envOverrides', { names: hostStatus.env_overrides.join(', ') })}
          </p>
        ) : null}
        <div className="bb-settings-row">
          <p className="bb-muted" data-testid="blackboard-settings-host-state" data-variant={running ? 'running' : 'stopped'}>
            {hostStatus?.error
              ? t('blackboard.settings.startError', { error: hostStatus.error })
              : running
                ? t('blackboard.settings.running', { address })
                : t('blackboard.settings.stopped')}
          </p>
          <Button variant="primary" loading={hostSubmit.busy} data-testid="blackboard-settings-apply-btn" onClick={() => void applyHosting()}>
            {t('blackboard.settings.apply')}
          </Button>
        </div>
        {running && health?.ok ? (
          <p className="bb-muted" data-testid="blackboard-settings-host-health">
            {t('blackboard.settings.health', {
              members: health.members_connected ?? 0,
              documents: docs?.open_documents ?? 0,
              waiting: health.queue_depth ?? 0,
            })}
            {docs?.pdf_export === false ? ` ${t('blackboard.settings.noPdf')}` : ''}
          </p>
        ) : null}
        {hostSubmit.error ? (
          <p className="bb-dialog-error" role="alert">
            {hostSubmit.error}
          </p>
        ) : null}
        {running && !hostStatus?.reachable_from_other_machines ? (
          <p className="bb-notice" data-testid="blackboard-settings-not-reachable">
            {t('blackboard.settings.notReachable')}
          </p>
        ) : null}
        {running && address.startsWith('http://') && hostStatus?.reachable_from_other_machines ? (
          <p className="bb-notice" data-testid="blackboard-settings-plain-http">
            {t('blackboard.settings.plainHttp')}
          </p>
        ) : null}
      </section>
      {open && hostName ? <AccessKey hostName={hostName} hostUrl={hostUrl} actions={access} /> : null}
      {open && hostName && isOperator ? <HostPeople actions={access} /> : null}
      {open && hostName ? <ConnectedAccounts hostName={hostName} changed={profile} actions={im} /> : null}
      {open && hostName && isOperator ? <HostBots actions={im} /> : null}
      {open ? <BotMode actions={im} /> : null}
    </FormDialog>
  );
}
