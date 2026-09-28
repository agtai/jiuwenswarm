import type { TFunction } from 'i18next';

import { errorText } from './controller';

// Codes the host and the client part return (common/errors.py). `invalid` and
// `conflict` keep the host's own message, which names the field or the rule.
const TRANSLATED = new Set([
  'unauthorized',
  'not_member',
  'forbidden',
  'not_found',
  'expired',
  'disabled',
  'unavailable',
  'internal',
]);

export function describeError(t: TFunction, error: unknown): string {
  const code = typeof error === 'object' && error !== null ? (error as { code?: unknown }).code : undefined;
  if (typeof code === 'string' && TRANSLATED.has(code)) return t(`blackboard.errors.${code}`);
  const text = errorText(error);
  return text || t('blackboard.errors.generic');
}
