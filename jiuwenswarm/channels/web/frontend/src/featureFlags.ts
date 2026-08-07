/**
 * 前端功能开关（集中管理，便于按构建裁剪 UI）
 */
export const FEATURE_APP_UPDATER_UI = true;

/** 两周 Live Voice 纵向 Demo；关闭时不挂载任何语音 UI。 */
export const FEATURE_LIVE_VOICE_DEMO = true;

/**
 * Post-V0 conservative sentence preview. Disabled by default so applying the
 * development stash cannot silently change the V0 acceptance behaviour.
 */
export const FEATURE_LIVE_VOICE_STREAMING_SPEECH = import.meta.env.VITE_FEATURE_LIVE_VOICE_STREAMING_SPEECH === 'true';

/**
 * Post-V0 restricted AutoHarness task bridge. Disabled by default because its
 * confirmed commands can create side-effecting background work.
 */
export const FEATURE_LIVE_VOICE_TASK_DEMO = import.meta.env.VITE_FEATURE_LIVE_VOICE_TASK_DEMO === 'true';

export const FEATURE_LIVE_VOICE_INTEGRATED_P1 = import.meta.env.VITE_FEATURE_LIVE_VOICE_INTEGRATED_P1 === 'true';

/**
 * Cumulative P1/P2/P3alpha Web composition shell and diagnostics. Disabled by
 * default: enabling the shell discloses route facts but does not make missing
 * formal adapters runnable or grant release/replacement credit.
 */
export const FEATURE_LIVE_VOICE_INTEGRATED_WEB = import.meta.env.VITE_FEATURE_LIVE_VOICE_INTEGRATED_WEB === 'true';

/** Destructive formal task control stays separately default-off. */
export const FEATURE_LIVE_VOICE_PRODUCT_P3_MUTATION = import.meta.env.VITE_FEATURE_LIVE_VOICE_PRODUCT_P3_MUTATION === 'true';
