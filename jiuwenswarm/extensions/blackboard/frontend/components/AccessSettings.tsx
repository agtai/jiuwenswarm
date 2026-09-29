// Access to a host (milestone 8), in the settings dialog: replacing this person's own key, the
// plain-HTTP warning for a host on another machine, and the operator's list of people on the host.
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { KeyRound, UserCheck, UserX } from 'lucide-react';

import { Button, toast } from '../../../../channels/web/frontend/src/components/ui';
import type { UserView } from '../types';

export interface AccessActions {
  rotateToken: () => Promise<void>;
  users: () => Promise<UserView[]>;
  setUserStatus: (userId: string, status: 'active' | 'disabled') => Promise<void>;
}

const message = (e: unknown) => (e instanceof Error ? e.message : String(e));
const LOOPBACK = new Set(['127.0.0.1', 'localhost', '[::1]', '::1']);

function plainHttpToAnotherMachine(url: string | null): boolean {
  if (!url) return false;
  try {
    const parsed = new URL(url);
    return parsed.protocol === 'http:' && !LOOPBACK.has(parsed.hostname);
  } catch {
    return false;
  }
}

export function AccessKey({ hostName, hostUrl, actions }: { hostName: string; hostUrl: string | null; actions: AccessActions }) {
  const { t } = useTranslation();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const rotate = async () => {
    setBusy(true);
    setError(null);
    try {
      await actions.rotateToken();
      toast.open({ content: t('blackboard.access.keyReplaced'), variant: 'success' });
    } catch (e) {
      setError(message(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="bb-settings-section" data-testid="blackboard-settings-access-key">
      <div className="bb-settings-row">
        <div>
          <h4>{t('blackboard.access.key')}</h4>
          <p className="bb-muted">{t('blackboard.access.keyHint', { host: hostName })}</p>
        </div>
        <Button size="sm" icon={<KeyRound size={14} />} loading={busy} data-testid="blackboard-access-rotate-btn" onClick={() => void rotate()}>
          {t('blackboard.access.replaceKey')}
        </Button>
      </div>
      {plainHttpToAnotherMachine(hostUrl) ? (
        <p className="bb-notice" data-testid="blackboard-access-plain-http">
          {t('blackboard.access.plainHttp', { host: hostName })}
        </p>
      ) : null}
      {error ? (
        <p className="bb-dialog-error" role="alert">
          {error}
        </p>
      ) : null}
    </section>
  );
}

// The operator's list: turning someone off ends their access to every workspace at once.
export function HostPeople({ actions }: { actions: AccessActions }) {
  const { t } = useTranslation();
  const [people, setPeople] = useState<UserView[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = () => actions.users().then(setPeople, (e) => setError(message(e)));
  useEffect(() => {
    void load();
  }, []);

  const set = (user: UserView, status: 'active' | 'disabled') => {
    setError(null);
    void actions.setUserStatus(user.id, status).then(load, (e) => setError(message(e)));
  };

  return (
    <section className="bb-settings-section" data-testid="blackboard-settings-people">
      <h4>{t('blackboard.access.people')}</h4>
      <p className="bb-muted">{t('blackboard.access.peopleHint')}</p>
      <ul className="bb-im-list">
        {people.map((u) => (
          <li key={u.id} data-testid="blackboard-person-item" data-variant={u.display_name} data-state={u.disabled ? 'disabled' : 'active'}>
            <span>
              <strong>{u.display_name}</strong>{' '}
              <span className="bb-muted">
                {u.is_operator
                  ? t('blackboard.access.operator')
                  : u.disabled
                    ? t('blackboard.access.disabled')
                    : t('blackboard.access.workspaces', { count: u.workspaces })}
              </span>
            </span>
            {u.is_operator ? null : u.disabled ? (
              <Button size="sm" variant="quiet" icon={<UserCheck size={14} />} data-testid="blackboard-person-enable-btn" onClick={() => set(u, 'active')}>
                {t('blackboard.access.enable')}
              </Button>
            ) : (
              <Button size="sm" variant="quiet" icon={<UserX size={14} />} data-testid="blackboard-person-disable-btn" onClick={() => set(u, 'disabled')}>
                {t('blackboard.access.disable')}
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
