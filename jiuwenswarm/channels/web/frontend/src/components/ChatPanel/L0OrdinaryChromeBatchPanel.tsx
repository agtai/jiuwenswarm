import React, { useEffect, useMemo, useRef, useState } from 'react';

import {
  OrdinaryChromeL0BatchController,
  parseOrdinaryChromeBatchConfig,
  type OrdinaryChromeBatchProgress,
  type OrdinaryChromeVoiceControl,
  type OrdinaryChromeVoiceState,
} from '../../features/live-voice/formal/l0OrdinaryChromeBatch.js';

const IDLE_PROGRESS: OrdinaryChromeBatchProgress = Object.freeze({
  status: 'idle',
  temperature: null,
  metric: null,
  first_audio_eligible: 0,
  barge_in_eligible: 0,
  target: 20,
  reason: null,
});

export function L0OrdinaryChromeBatchPanel(props: Readonly<{
  control: OrdinaryChromeVoiceControl | null;
  state: OrdinaryChromeVoiceState | null;
  connected: boolean;
}>): React.ReactElement | null {
  const config = useMemo(
    () => parseOrdinaryChromeBatchConfig(typeof window === 'undefined' ? '' : window.location.search),
    [],
  );
  const controlRef = useRef(props.control);
  const stateRef = useRef(props.state);
  const connectedRef = useRef(props.connected);
  const controllerRef = useRef<OrdinaryChromeL0BatchController | null>(null);
  const [progress, setProgress] = useState(IDLE_PROGRESS);
  controlRef.current = props.control;
  stateRef.current = props.state;
  connectedRef.current = props.connected;

  useEffect(() => {
    if (config === null) return;
    const controller = new OrdinaryChromeL0BatchController(config, {
      getControl: () => controlRef.current,
      getState: () => stateRef.current,
      getConnected: () => connectedRef.current,
      onProgress: setProgress,
    });
    controllerRef.current = controller;
    return () => {
      if (controllerRef.current === controller) controllerRef.current = null;
      void controller.close();
    };
  }, [config]);

  if (config === null) return null;
  const running = ['connecting', 'warming', 'running', 'settling', 'waiting_epoch'].includes(progress.status);
  const metric = progress.metric === 'first_audio'
    ? '首音频'
    : progress.metric === 'barge_in'
      ? '打断'
      : '—';
  return (
    <aside
      className="fixed bottom-5 right-5 z-[1000] w-80 rounded-lg border border-sky-500 bg-white p-4 text-sm shadow-xl dark:bg-slate-900"
      data-testid="l0-ordinary-chrome-batch"
      aria-label="L0 ordinary Chrome batch"
    >
      <div className="font-semibold">L0 普通 Chrome 自动批次</div>
      <div className="mt-1 text-xs text-text-muted">
        预录语料；Browser 数字指标；不声明逐轮物理验收
      </div>
      <dl className="mt-3 grid grid-cols-2 gap-1 text-xs">
        <dt>状态</dt><dd>{progress.status === 'settling' ? 'settling（后继回答排空）' : progress.status}</dd>
        <dt>温度</dt><dd>{progress.temperature ?? '—'}</dd>
        <dt>当前指标</dt><dd>{metric}</dd>
        <dt>首音频</dt><dd>{progress.first_audio_eligible}/{progress.target}</dd>
        <dt>打断</dt><dd>{progress.barge_in_eligible}/{progress.target}</dd>
      </dl>
      {progress.reason !== null && (
        <div className={`mt-2 text-xs ${progress.status === 'failed' ? 'text-red-600' : 'text-text-muted'}`}>
          {progress.reason === 'successor_playout_not_measured'
            ? '这段播放不计入打断耗时；结束后才切换下一组测量标签。'
            : progress.reason}
        </div>
      )}
      <div className="mt-3 flex gap-2">
        <button
          type="button"
          className="rounded bg-sky-600 px-3 py-1.5 text-white disabled:opacity-50"
          disabled={running || progress.status === 'complete' || props.control === null}
          onClick={() => void controllerRef.current?.run().catch(() => undefined)}
        >
          {progress.status === 'idle' ? '开始自动批次' : '继续自动批次'}
        </button>
        <button
          type="button"
          className="rounded border px-3 py-1.5 disabled:opacity-50"
          disabled={!running}
          onClick={() => controllerRef.current?.cancel()}
        >
          停止
        </button>
      </div>
    </aside>
  );
}
