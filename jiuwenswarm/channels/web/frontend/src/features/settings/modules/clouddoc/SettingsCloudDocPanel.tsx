/**
 * Cloud-doc connections, as a Settings module (§25.3).
 *
 * This is the accession surface — keys and connectivity, ring ① of the mandate.
 * What the agent may do once connected (watches, receipts, revert) stays in the
 * Docs acceptance console; this page only manages who the deployment can reach
 * the platforms as.
 */
import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { webRequest } from '../../../../services/webClient';
import ModelPicker from '../../../../components/ModelPicker';

type Connection = {
  id: string;
  provider: string;
  provider_name?: string;
  agent_address?: string | null;
  agent_display?: string;
  kind?: 'service' | 'personal';
  docs_count?: number;
};

type SavedKey = { filename: string; path: string; client_email?: string; address?: string; in_use?: boolean };

export const CLOUDDOC_CONNECTIONS_CHANGED = 'jiuwen:clouddoc-connections-changed';

export function SettingsCloudDocPanel({ isConnected }: { isConnected: boolean }) {
  const { t } = useTranslation();
  const [conns, setConns] = useState<Connection[]>([]);
  const [savedKeys, setSavedKeys] = useState<SavedKey[]>([]);
  const [keyText, setKeyText] = useState('');
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState('');
  const [modelName, setModelName] = useState('');
  // S.5: the person's half of the personal signature. The receipt number is
  // appended by the server and is not editable here.
  const [signature, setSignature] = useState('');
  const [signatureSaved, setSignatureSaved] = useState('');
  // Google personal identity: an OAuth client the self-hoster registered, then a
  // consent flow that comes back on a loopback port (or a pasted code).
  const [gClientId, setGClientId] = useState('');
  const [gClientSecret, setGClientSecret] = useState('');
  const [gConfigured, setGConfigured] = useState(false);
  const [gFlow, setGFlow] = useState<{ state: string; auth_url: string; redirect_uri: string } | null>(null);
  const [gStatus, setGStatus] = useState<{ status: string; detail?: string } | null>(null);
  const [gCode, setGCode] = useState('');
  // Feishu personal identity: the device-code login, entirely inside the swarm --
  // a QR code, the link and the user code, polled until the person has scanned.
  const [fFlow, setFFlow] = useState<{ state: string; verification_url: string; user_code: string; qr_png_base64: string; expires_at: number } | null>(null);
  const [fStatus, setFStatus] = useState<{ status: string; detail?: string } | null>(null);

  const refresh = useCallback(async () => {
    try {
      const conf = await webRequest<{ enabled: boolean; connections?: Connection[]; model_name?: string; personal_signature?: string }>(
        'clouddoc.get_conf',
      );
      setConns(conf?.connections ?? []);
      setModelName(conf?.model_name ?? '');
      setSignature(conf?.personal_signature ?? '');
      setSignatureSaved(conf?.personal_signature ?? '');
      const g = (conf as { google_oauth?: { configured?: boolean; client_id?: string } } | null)?.google_oauth;
      setGConfigured(!!g?.configured);
      setGClientId(g?.client_id ?? '');
      const keys = await webRequest<{ keys?: SavedKey[] }>('clouddoc.list_keys');
      setSavedKeys(keys?.keys ?? []);
    } catch (e) {
      setNote(String(e));
    }
  }, []);

  useEffect(() => {
    if (isConnected) void refresh();
  }, [isConnected, refresh]);

  const announce = () => window.dispatchEvent(new CustomEvent(CLOUDDOC_CONNECTIONS_CHANGED));

  const addFromText = async () => {
    if (!keyText.trim()) return;
    setBusy(true);
    setNote('');
    try {
      const out = await webRequest<{ ok?: boolean; detail?: string }>(
        'clouddoc.add_connection', { credentials_json: keyText },
      );
      setNote(out?.detail || t('settingsPanel.clouddoc.added'));
      setKeyText('');
      await refresh();
      announce();
    } catch (e) {
      setNote(String(e));
    } finally {
      setBusy(false);
    }
  };

  const addFromSaved = async (path: string) => {
    setBusy(true);
    setNote('');
    try {
      const out = await webRequest<{ ok?: boolean; detail?: string }>(
        'clouddoc.add_connection', { credentials_path: path },
      );
      setNote(out?.detail || t('settingsPanel.clouddoc.added'));
      await refresh();
      announce();
    } catch (e) {
      setNote(String(e));
    } finally {
      setBusy(false);
    }
  };

  // S.1: connect as the person themselves. No key to paste -- the identity is
  // whatever lark-cli is logged in as, and a missing login is reported with the
  // command to run.
  const addPersonal = async () => {
    setBusy(true);
    setNote('');
    setFStatus(null);
    try {
      // A user already logged in connects straight away; otherwise the device
      // flow starts and the QR code below takes over.
      const start = await webRequest<{ result: string; detail?: string; state?: string; verification_url?: string; user_code?: string; qr_png_base64?: string; expires_at?: number }>(
        'clouddoc.feishu_login_start',
      );
      if (start?.result === 'ok' && start.state) {
        setFFlow({
          state: start.state,
          verification_url: start.verification_url ?? '',
          user_code: start.user_code ?? '',
          qr_png_base64: start.qr_png_base64 ?? '',
          expires_at: start.expires_at ?? 0,
        });
        setFStatus({ status: 'pending' });
        return;
      }
      if (start?.result !== 'already') {
        setFStatus({ status: 'error', detail: start?.detail || start?.result || '' });
        return;
      }
      const out = await webRequest<{ result?: string; detail?: string }>(
        'clouddoc.add_personal_connection', { brand: 'feishu' },
      );
      if (out?.result === 'ok') setNote(t('settingsPanel.clouddoc.personalAdded'));
      else setNote(out?.detail || out?.result || '');
      await refresh();
      announce();
    } catch (e) {
      setNote(String(e));
    } finally {
      setBusy(false);
    }
  };

  // The login finishes on its own once the person has scanned; poll every 3s.
  useEffect(() => {
    if (!fFlow || fStatus?.status !== 'pending') return;
    const id = window.setInterval(() => {
      void webRequest<{ status: string; detail?: string }>('clouddoc.feishu_login_status', { state: fFlow.state })
        .then((s) => {
          if (!s) return;
          setFStatus(s);
          if (s.status === 'done') { void refresh(); announce(); }
        })
        .catch(() => undefined);
    }, 3000);
    return () => window.clearInterval(id);
  }, [fFlow, fStatus?.status, refresh]);

  const saveSignature = async () => {
    setBusy(true);
    setNote('');
    try {
      const out = await webRequest<{ ok?: boolean; personal_signature?: string; preview?: string }>(
        'clouddoc.set_signature', { text: signature },
      );
      setSignature(out?.personal_signature ?? '');
      setSignatureSaved(out?.personal_signature ?? '');
      setNote(t('settingsPanel.clouddoc.signatureSaved', { preview: out?.preview ?? '' }));
    } catch (e) {
      setNote(String(e));
    } finally {
      setBusy(false);
    }
  };

  const saveGoogleClient = async () => {
    setBusy(true);
    setNote('');
    try {
      const out = await webRequest<{ ok?: boolean; configured?: boolean }>(
        'clouddoc.google_oauth_configure', { client_id: gClientId, client_secret: gClientSecret },
      );
      setGConfigured(!!out?.configured);
      setGClientSecret('');
      setNote(out?.configured ? t('settingsPanel.clouddoc.googleClientSaved') : t('settingsPanel.clouddoc.googleClientCleared'));
    } catch (e) {
      setNote(String(e));
    } finally {
      setBusy(false);
    }
  };

  const startGoogle = async () => {
    setBusy(true);
    setNote('');
    setGStatus(null);
    try {
      const out = await webRequest<{ result: string; detail?: string; state?: string; auth_url?: string; redirect_uri?: string }>(
        'clouddoc.google_oauth_start',
      );
      if (out?.result !== 'ok' || !out.state || !out.auth_url) {
        setNote(out?.detail || out?.result || '');
        return;
      }
      setGFlow({ state: out.state, auth_url: out.auth_url, redirect_uri: out.redirect_uri ?? '' });
      setGStatus({ status: 'pending' });
      window.open(out.auth_url, '_blank', 'noopener');
    } catch (e) {
      setNote(String(e));
    } finally {
      setBusy(false);
    }
  };

  // The flow finishes on its own when the browser comes back; poll until then.
  useEffect(() => {
    if (!gFlow || gStatus?.status !== 'pending') return;
    const id = window.setInterval(() => {
      void webRequest<{ status: string; detail?: string }>('clouddoc.google_oauth_status', { state: gFlow.state })
        .then((s) => {
          if (!s) return;
          setGStatus(s);
          if (s.status === 'done') { void refresh(); announce(); }
        })
        .catch(() => undefined);
    }, 2000);
    return () => window.clearInterval(id);
  }, [gFlow, gStatus?.status, refresh]);

  const finishGoogle = async () => {
    if (!gFlow || !gCode.trim()) return;
    setBusy(true);
    try {
      const s = await webRequest<{ status: string; detail?: string }>(
        'clouddoc.google_oauth_finish', { state: gFlow.state, code: gCode.trim() },
      );
      setGStatus(s);
      if (s?.status === 'done') { setGCode(''); await refresh(); announce(); }
    } catch (e) {
      setNote(String(e));
    } finally {
      setBusy(false);
    }
  };

  const removeConn = async (id: string) => {
    // Removing a connection is a grant-lifecycle act: every watch issued under it
    // stops meaning anything. The confirm says so before anything happens.
    if (!window.confirm(t('settingsPanel.clouddoc.removeConfirm'))) return;
    setBusy(true);
    try {
      await webRequest('clouddoc.remove_connection', { connection_id: id });
      await refresh();
      announce();
    } catch (e) {
      setNote(String(e));
    } finally {
      setBusy(false);
    }
  };

  // Deployment-wide, like the mode: one model for every unattended turn. Empty
  // restores the agentserver's default. Validation happens server-side.
  const setModel = async (name: string) => {
    setBusy(true);
    setNote('');
    try {
      const out = await webRequest<{ ok?: boolean; detail?: string; model_name?: string }>(
        'clouddoc.set_model', { model_name: name },
      );
      if (out?.ok === false) {
        setNote(out.detail || '');
        return;
      }
      setModelName(out?.model_name ?? name);
    } catch (e) {
      setNote(String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div data-testid="settings-clouddoc-panel" className="flex flex-col gap-4 text-sm">
      <div>
        <div className="font-medium mb-2">{t('settingsPanel.clouddoc.connectionsTitle')}</div>
        {conns.length === 0 && (
          <div className="text-text-muted">{t('settingsPanel.clouddoc.noConnections')}</div>
        )}
        {conns.map((c) => (
          <div
            key={c.id}
            data-testid="settings-clouddoc-connection"
            className="flex items-center justify-between rounded-md border border-border px-3 py-2 mb-2"
          >
            <div className="min-w-0">
              <div className="font-medium">
                {c.provider_name || c.provider}
                <span
                  className={`ml-2 rounded px-1.5 py-0.5 text-[10px] ${c.kind === 'personal' ? 'bg-violet-50 text-violet-700' : 'bg-bg-muted text-text-muted'}`}
                  data-testid="settings-clouddoc-kind"
                >
                  {c.kind === 'personal' ? t('settingsPanel.clouddoc.kindPersonal') : t('settingsPanel.clouddoc.kindService')}
                </span>
                {c.kind === 'personal' && c.agent_display ? <span className="ml-2 text-xs text-text-muted">{c.agent_display}</span> : null}
              </div>
              <div className="text-xs text-text-muted truncate">
                {c.agent_address}
                {typeof c.docs_count === 'number'
                  ? ` · ${t('settingsPanel.clouddoc.docsCount', { n: c.docs_count })}` : ''}
              </div>
            </div>
            <div className="flex items-center gap-2 flex-none">
              {c.agent_address && (
                <button
                  className="text-xs underline"
                  onClick={() => void navigator.clipboard?.writeText(c.agent_address || '')}
                >
                  {t('settingsPanel.clouddoc.copyAddress')}
                </button>
              )}
              <button
                data-testid="settings-clouddoc-remove"
                className="text-xs text-red-600 underline"
                disabled={busy}
                onClick={() => void removeConn(c.id)}
              >
                {t('settingsPanel.clouddoc.remove')}
              </button>
            </div>
          </div>
        ))}
      </div>

      <div data-testid="settings-clouddoc-model">
        <div className="font-medium mb-1">{t('settingsPanel.clouddoc.modelTitle')}</div>
        <div className="text-xs text-text-muted mb-2">{t('settingsPanel.clouddoc.modelHint')}</div>
        <div className="flex items-center gap-3">
          <ModelPicker
            testIdPrefix="settings-clouddoc-model-picker"
            value={modelName || null}
            onChange={(name) => void setModel(name)}
            disabled={busy}
          />
          {modelName ? (
            <button
              data-testid="settings-clouddoc-model-reset"
              className="text-xs underline"
              disabled={busy}
              onClick={() => void setModel('')}
            >
              {t('settingsPanel.clouddoc.modelUseDefault')}
            </button>
          ) : (
            <span className="text-xs text-text-muted">{t('settingsPanel.clouddoc.modelDefault')}</span>
          )}
        </div>
      </div>

      <div data-testid="settings-clouddoc-personal">
        <div className="font-medium mb-1">{t('settingsPanel.clouddoc.personalTitle')}</div>
        <div className="text-xs text-text-muted mb-2">{t('settingsPanel.clouddoc.personalModel')}</div>
        <div className="rounded-md border border-border p-3" data-testid="settings-clouddoc-feishu-personal">
          <div className="text-xs font-medium mb-1">{t('settingsPanel.clouddoc.feishuPersonalTitle')}</div>
          <div className="text-xs text-text-muted mb-2">{t('settingsPanel.clouddoc.personalHint')}</div>
          <div className="flex items-center gap-2">
            <button
              data-testid="settings-clouddoc-add-personal"
              className="rounded-md border border-border px-3 py-1.5"
              disabled={busy || fStatus?.status === 'pending'}
              onClick={() => void addPersonal()}
            >
              {fStatus?.status === 'error' || fStatus?.status === 'denied' || fStatus?.status === 'expired'
                ? t('settingsPanel.clouddoc.feishuRetry')
                : t('settingsPanel.clouddoc.personalConnect')}
            </button>
            {fStatus?.status === 'pending' && <span className="text-xs text-text-muted">{t('settingsPanel.clouddoc.feishuWaiting')}</span>}
            {fStatus?.status === 'done' && <span className="text-xs text-green-700">{t('settingsPanel.clouddoc.feishuDone')}</span>}
            {(fStatus?.status === 'error' || fStatus?.status === 'denied' || fStatus?.status === 'expired') && (
              <span className="text-xs text-red-600" data-testid="settings-clouddoc-feishu-error">
                {fStatus.status === 'expired' ? t('settingsPanel.clouddoc.feishuExpired') : fStatus.status === 'denied' ? t('settingsPanel.clouddoc.feishuDenied') : ''}
                {fStatus.detail ? ` ${fStatus.detail}` : ''}
              </span>
            )}
          </div>
          {fFlow && fStatus?.status === 'pending' && (
            <div className="mt-2 flex items-start gap-4" data-testid="settings-clouddoc-feishu-qr">
              {fFlow.qr_png_base64 ? (
                <img
                  src={`data:image/png;base64,${fFlow.qr_png_base64}`}
                  alt="QR"
                  width={160}
                  height={160}
                  className="flex-none rounded-md border border-border bg-white"
                  data-testid="settings-clouddoc-feishu-qr-img"
                />
              ) : null}
              <div className="text-xs leading-relaxed">
                <div>{t('settingsPanel.clouddoc.feishuScanHint')}</div>
                <div className="mt-1">
                  {t('settingsPanel.clouddoc.feishuUserCode')}{' '}
                  <span className="rounded bg-bg-muted px-1.5 py-0.5 font-mono text-sm" data-testid="settings-clouddoc-feishu-user-code">{fFlow.user_code}</span>
                </div>
                <div className="mt-1">
                  <a className="text-text-link underline break-all" href={fFlow.verification_url} target="_blank" rel="noreferrer">
                    {t('settingsPanel.clouddoc.feishuOpenLink')}
                  </a>
                </div>
                {fFlow.expires_at > 0 && (
                  <div className="mt-1 text-text-muted">{t('settingsPanel.clouddoc.feishuExpiresAt', { time: new Date(fFlow.expires_at * 1000).toLocaleTimeString() })}</div>
                )}
              </div>
            </div>
          )}
        </div>
        <div className="mt-3 rounded-md border border-border p-3" data-testid="settings-clouddoc-google-personal">
          <div className="text-xs font-medium mb-1">{t('settingsPanel.clouddoc.googlePersonalTitle')}</div>
          <div className="text-xs text-text-muted mb-2">{t('settingsPanel.clouddoc.googlePersonalHint')}</div>
          <div className="flex flex-col gap-1.5">
            <input
              data-testid="settings-clouddoc-google-client-id"
              className="rounded-md border border-border px-2 py-1 text-xs font-mono"
              placeholder="client_id (…apps.googleusercontent.com)"
              value={gClientId}
              onChange={(e) => setGClientId(e.target.value)}
            />
            <input
              data-testid="settings-clouddoc-google-client-secret"
              type="password"
              className="rounded-md border border-border px-2 py-1 text-xs font-mono"
              placeholder={gConfigured ? t('settingsPanel.clouddoc.googleSecretKept') : 'client_secret'}
              value={gClientSecret}
              onChange={(e) => setGClientSecret(e.target.value)}
            />
            <div className="flex items-center gap-2">
              <button
                data-testid="settings-clouddoc-google-save"
                className="rounded-md border border-border px-3 py-1 text-xs"
                disabled={busy || (!!gClientId && !gClientSecret && !gConfigured)}
                onClick={() => void saveGoogleClient()}
              >
                {t('settingsPanel.clouddoc.googleClientSave')}
              </button>
              <button
                data-testid="settings-clouddoc-google-authorize"
                className="rounded-md border border-border px-3 py-1 text-xs"
                disabled={busy || !gConfigured}
                onClick={() => void startGoogle()}
              >
                {t('settingsPanel.clouddoc.googleAuthorize')}
              </button>
              {gStatus?.status === 'pending' && <span className="text-xs text-text-muted">{t('settingsPanel.clouddoc.googleWaiting')}</span>}
              {gStatus?.status === 'done' && <span className="text-xs text-green-700">{t('settingsPanel.clouddoc.googleDone')}</span>}
              {gStatus?.status === 'error' && <span className="text-xs text-red-600">{gStatus.detail}</span>}
            </div>
            {gFlow && gStatus?.status === 'pending' && (
              <div className="mt-1 text-xs text-text-muted" data-testid="settings-clouddoc-google-fallback">
                <div>
                  {t('settingsPanel.clouddoc.googleLinkHint')}{' '}
                  <a className="text-text-link underline" href={gFlow.auth_url} target="_blank" rel="noreferrer">{t('settingsPanel.clouddoc.googleOpenLink')}</a>
                  {' · '}{t('settingsPanel.clouddoc.googleRedirect', { uri: gFlow.redirect_uri })}
                </div>
                <div className="mt-1 flex items-center gap-2">
                  <input
                    className="flex-1 rounded-md border border-border px-2 py-1 text-xs font-mono"
                    placeholder={t('settingsPanel.clouddoc.googleCodePlaceholder')}
                    value={gCode}
                    onChange={(e) => setGCode(e.target.value)}
                  />
                  <button className="rounded-md border border-border px-3 py-1 text-xs" disabled={busy || !gCode.trim()} onClick={() => void finishGoogle()}>
                    {t('settingsPanel.clouddoc.googleFinish')}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
        <div className="mt-3">
          <div className="text-xs font-medium mb-1">{t('settingsPanel.clouddoc.signatureTitle')}</div>
          <div className="text-xs text-text-muted mb-1">{t('settingsPanel.clouddoc.signatureHint')}</div>
          <div className="flex items-center gap-2">
            <input
              data-testid="settings-clouddoc-signature"
              className="flex-1 rounded-md border border-border px-2 py-1 text-xs"
              placeholder={t('settingsPanel.clouddoc.signatureDefault')}
              value={signature}
              onChange={(e) => setSignature(e.target.value)}
            />
            <button
              data-testid="settings-clouddoc-signature-save"
              className="rounded-md border border-border px-3 py-1 text-xs"
              disabled={busy || signature === signatureSaved}
              onClick={() => void saveSignature()}
            >
              {t('settingsPanel.clouddoc.signatureSave')}
            </button>
          </div>
          <div className="mt-1 text-[11px] text-text-muted">{t('settingsPanel.clouddoc.signatureTail')}</div>
        </div>
      </div>

      <div>
        <div className="font-medium mb-1">{t('settingsPanel.clouddoc.addTitle')}</div>
        <div className="text-xs text-text-muted mb-2">{t('settingsPanel.clouddoc.addHint')}</div>
        <textarea
          data-testid="settings-clouddoc-key-input"
          className="w-full h-28 rounded-md border border-border p-2 font-mono text-xs"
          placeholder='{"type": "service_account", ...}  |  {"app_id": "cli_...", "app_secret": "..."}'
          value={keyText}
          onChange={(e) => setKeyText(e.target.value)}
        />
        <button
          data-testid="settings-clouddoc-add"
          className="mt-2 rounded-md border border-border px-3 py-1.5"
          disabled={busy || !keyText.trim()}
          onClick={() => void addFromText()}
        >
          {t('settingsPanel.clouddoc.add')}
        </button>
        {savedKeys.length > 0 && (
          <div className="mt-3">
            <div className="text-xs text-text-muted mb-1">{t('settingsPanel.clouddoc.savedKeys')}</div>
            {savedKeys.filter((k) => !k.in_use).map((k) => (
              <button
                key={k.filename}
                className="mr-2 mb-1 rounded-md border border-border px-2 py-1 text-xs"
                disabled={busy}
                onClick={() => void addFromSaved(k.path)}
              >
                {k.address || k.client_email || k.filename}
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="rounded-md bg-bg-hover p-3 text-xs leading-relaxed">
        <div className="font-medium mb-1">{t('settingsPanel.clouddoc.guideTitle')}</div>
        <div>{t('settingsPanel.clouddoc.guideApis')}</div>
        <div>{t('settingsPanel.clouddoc.guideShare')}</div>
      </div>

      {note && <div data-testid="settings-clouddoc-note" className="text-xs">{note}</div>}
    </div>
  );
}
