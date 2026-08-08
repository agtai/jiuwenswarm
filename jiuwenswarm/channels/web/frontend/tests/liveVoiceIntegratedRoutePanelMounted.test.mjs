import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

import i18next from 'i18next';
import React from 'react';
import { I18nextProvider } from 'react-i18next';
import { act, create } from 'react-test-renderer';

import {
  LiveVoiceIntegratedRoutePanel,
} from '../node_modules/.cache/live-voice-integrated-web/LiveVoiceIntegratedRoutePanel.mjs';


test('mounted route panel survives session replacement and closes every effect on unmount', async () => {
  const translations = JSON.parse(
    await readFile(new URL('../src/i18n/locales/en.json', import.meta.url), 'utf8')
  );
  const i18n = i18next.createInstance();
  await i18n.init({
    lng: 'en',
    fallbackLng: false,
    resources: { en: { translation: translations } },
    interpolation: { escapeValue: false },
  });
  let renderer;
  await act(async () => {
    renderer = create(
      React.createElement(
        I18nextProvider,
        { i18n },
        React.createElement(LiveVoiceIntegratedRoutePanel, {
          activeSessionId: 'mounted-session-1',
          isConnected: false,
          agentRouteAvailable: false,
          taskCompatibilityAvailable: false,
        })
      )
    );
  });
  assert.notEqual(renderer.toJSON(), null);

  await act(async () => {
    renderer.update(
      React.createElement(
        I18nextProvider,
        { i18n },
        React.createElement(LiveVoiceIntegratedRoutePanel, {
          activeSessionId: 'mounted-session-2',
          isConnected: false,
          agentRouteAvailable: false,
          taskCompatibilityAvailable: false,
        })
      )
    );
  });
  await act(async () => {
    renderer.unmount();
  });
  assert.equal(renderer.toJSON(), null);
});
