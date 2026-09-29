// Reading Blackboard from IM (milestone 7), in the settings dialog: the IM accounts a person connects
// to their user for a team's shared bot, the bots a host's operator makes, and the bot links a
// jiuwenswarm keeps when it is that shared bot.
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Bot, Copy, Link2, Plus, Trash2, Unlink } from 'lucide-react';

import { Button, Input, toast } from '../../../../channels/web/frontend/src/components/ui';
import type { BotLinkView, BotView, IdentityView } from '../types';

export interface ImActions {
  accounts: () => Promise<IdentityView[]>;
  linkCode: () => Promise<{ code: string; expires_at: string }>;
  unlink: (platform: string, externalId: string) => Promise<void>;
  bots: () => Promise<BotView[]>;
  createBot: (name: string) => Promise<{ bot: BotView; link: string }>;
  revokeBot: (botId: string) => Promise<void>;
  botLinks: () => Promise<BotLinkView[]>;
  connectBot: (link: string) => Promise<BotLinkView[]>;
  removeBotLink: (id: string) => Promise<BotLinkView[]>;
}

const message = (e: unknown) => (e instanceof Error ? e.message : String(e));

async function copy(text: string, done: string): Promise<void> {
  await navigator.clipboard.writeText(text);
  toast.open({ content: done, variant: 'success' });
}

// `changed` moves when the person's profile reloads (a bot connected an account for them).
export function ConnectedAccounts({ hostName, changed, actions }: { hostName: string; changed: unknown; actions: ImActions }) {
  const { t } = useTranslation();
  const [accounts, setAccounts] = useState<IdentityView[] | null>(null);
  const [code, setCode] = useState<{ code: string; expires_at: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () => actions.accounts().then(setAccounts, (e) => setError(message(e)));
  useEffect(() => {
    void load();
  }, [changed]);
  // A new connection means the code was used.
  useEffect(() => {
    setCode(null);
  }, [accounts?.length]);

  const connect = async () => {
    setError(null);
    try {
      setCode(await actions.linkCode());
    } catch (e) {
      setError(message(e));
    }
  };

  return (
    <section className="bb-settings-section" data-testid="blackboard-settings-im-accounts">
      <div className="bb-settings-row">
        <div>
          <h4>{t('blackboard.im.accounts')}</h4>
          <p className="bb-muted">{t('blackboard.im.accountsHint', { host: hostName })}</p>
        </div>
        <Button size="sm" icon={<Link2 size={14} />} data-testid="blackboard-im-connect-btn" onClick={() => void connect()}>
          {t('blackboard.im.connect')}
        </Button>
      </div>
      {code ? (
        <div className="bb-im-code" data-testid="blackboard-im-code">
          <p>{t('blackboard.im.codeHint')}</p>
          <div className="bb-im-code__line">
            <code data-testid="blackboard-im-code-text">@bb link {code.code}</code>
            <Button size="sm" variant="quiet" icon={<Copy size={14} />} data-testid="blackboard-im-code-copy-btn" onClick={() => void copy(`@bb link ${code.code}`, t('blackboard.im.copied'))}>
              {t('blackboard.im.copy')}
            </Button>
          </div>
        </div>
      ) : null}
      {accounts && accounts.length === 0 ? (
        <p className="bb-muted" data-testid="blackboard-im-accounts-empty">
          {t('blackboard.im.noAccounts')}
        </p>
      ) : null}
      <ul className="bb-im-list">
        {(accounts ?? []).map((a) => (
          <li key={`${a.platform}:${a.external_id}`} data-testid="blackboard-im-account" data-variant={`${a.platform}:${a.external_id}`}>
            <span>
              <strong>{a.platform}</strong> <span className="bb-muted">{a.display_name || a.external_id}</span>
            </span>
            <Button
              size="sm"
              variant="quiet"
              icon={<Unlink size={14} />}
              data-testid="blackboard-im-disconnect-btn"
              onClick={() => void actions.unlink(a.platform, a.external_id).then(load, (e) => setError(message(e)))}
            >
              {t('blackboard.im.disconnect')}
            </Button>
          </li>
        ))}
      </ul>
      {error ? (
        <p className="bb-dialog-error" role="alert">
          {error}
        </p>
      ) : null}
    </section>
  );
}

// The host operator's shared bots: a new bot's link is shown once.
export function HostBots({ actions }: { actions: ImActions }) {
  const { t } = useTranslation();
  const [bots, setBots] = useState<BotView[]>([]);
  const [name, setName] = useState('');
  const [made, setMade] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = () => actions.bots().then(setBots, (e) => setError(message(e)));
  useEffect(() => {
    void load();
  }, []);

  const create = async () => {
    setError(null);
    try {
      const result = await actions.createBot(name.trim());
      setMade(result.link);
      setName('');
      await load();
    } catch (e) {
      setError(message(e));
    }
  };

  return (
    <section className="bb-settings-section" data-testid="blackboard-settings-bots">
      <h4>{t('blackboard.im.bots')}</h4>
      <p className="bb-muted">{t('blackboard.im.botsHint')}</p>
      <div className="bb-im-form">
        <Input value={name} maxLength={60} placeholder={t('blackboard.im.botName')} data-testid="blackboard-bot-name-input" onChange={setName} />
        <Button size="sm" icon={<Plus size={14} />} disabled={!name.trim()} data-testid="blackboard-bot-create-btn" onClick={() => void create()}>
          {t('blackboard.im.createBot')}
        </Button>
      </div>
      {made ? (
        <div className="bb-im-code" data-testid="blackboard-bot-link">
          <p>{t('blackboard.im.botLinkHint')}</p>
          <div className="bb-im-code__line">
            <code data-testid="blackboard-bot-link-text">{made}</code>
            <Button size="sm" variant="quiet" icon={<Copy size={14} />} data-testid="blackboard-bot-link-copy-btn" onClick={() => void copy(made, t('blackboard.im.copied'))}>
              {t('blackboard.im.copy')}
            </Button>
          </div>
        </div>
      ) : null}
      <ul className="bb-im-list">
        {bots.map((b) => (
          <li key={b.id} data-testid="blackboard-bot-item" data-variant={b.name}>
            <span>
              <Bot size={14} aria-hidden="true" /> <strong>{b.name}</strong>{' '}
              <span className="bb-muted">{b.revoked ? t('blackboard.im.revoked') : b.last_used_at ? t('blackboard.im.lastUsed', { time: new Date(b.last_used_at).toLocaleString() }) : t('blackboard.im.neverUsed')}</span>
            </span>
            {b.revoked ? null : (
              <Button size="sm" variant="quiet" icon={<Trash2 size={14} />} data-testid="blackboard-bot-revoke-btn" onClick={() => void actions.revokeBot(b.id).then(load, (e) => setError(message(e)))}>
                {t('blackboard.im.revoke')}
              </Button>
            )}
          </li>
        ))}
      </ul>
      {error ? (
        <p className="bb-dialog-error" role="alert">
          {error}
        </p>
      ) : null}
    </section>
  );
}

// This jiuwenswarm as a team's shared bot: the bot links it keeps.
export function BotMode({ actions }: { actions: ImActions }) {
  const { t } = useTranslation();
  const [links, setLinks] = useState<BotLinkView[]>([]);
  const [link, setLink] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    actions.botLinks().then(setLinks, (e) => setError(message(e)));
  }, []);

  const connect = async () => {
    setBusy(true);
    setError(null);
    try {
      setLinks(await actions.connectBot(link.trim()));
      setLink('');
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="bb-settings-section" data-testid="blackboard-settings-bot-mode">
      <h4>{t('blackboard.im.botMode')}</h4>
      <p className="bb-muted">{links.length ? t('blackboard.im.botModeOn') : t('blackboard.im.botModeHint')}</p>
      <ul className="bb-im-list">
        {links.map((b) => (
          <li key={b.id} data-testid="blackboard-bot-link-item" data-variant={b.bot_name}>
            <span>
              <strong>{b.host_name || b.url}</strong> <span className="bb-muted">{b.bot_name}</span>
            </span>
            <Button size="sm" variant="quiet" icon={<Trash2 size={14} />} data-testid="blackboard-bot-link-remove-btn" onClick={() => void actions.removeBotLink(b.id).then(setLinks, (e) => setError(message(e)))}>
              {t('blackboard.im.remove')}
            </Button>
          </li>
        ))}
      </ul>
      <div className="bb-im-form">
        <Input value={link} placeholder="https://.../blackboard/bot#bbb_..." data-testid="blackboard-bot-link-input" onChange={setLink} />
        <Button size="sm" loading={busy} disabled={!link.trim()} data-testid="blackboard-bot-connect-btn" onClick={() => void connect()}>
          {t('blackboard.im.connectBot')}
        </Button>
      </div>
      {error ? (
        <p className="bb-dialog-error" role="alert">
          {error}
        </p>
      ) : null}
    </section>
  );
}
