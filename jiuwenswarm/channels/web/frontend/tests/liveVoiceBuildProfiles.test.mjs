import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

const frontendRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repoRoot = resolve(frontendRoot, "..", "..", "..", "..");

const formalLiveVoiceFlags = [
  "VITE_FEATURE_LIVE_VOICE_INTEGRATED_WEB",
  "VITE_FEATURE_LIVE_VOICE_INTEGRATED_P1",
  "VITE_FEATURE_LIVE_VOICE_PRODUCT_P3_MUTATION",
];

const controlledRuntimeFlags = [
  "JIUWENSWARM_ENABLE_ORIGIN_CHECK",
  "JIUWENSWARM_LIVE_VOICE_P3_ENABLED",
  "JIUWENSWARM_LIVE_VOICE_PRODUCT_COMPOSITION_ENABLED",
  "JIUWENSWARM_LIVE_VOICE_PRODUCT_P2_ENABLED",
  "JIUWENSWARM_LIVE_VOICE_PRODUCT_P3_TEXT_ENABLED",
  "JIUWENSWARM_LIVE_VOICE_PRODUCT_P3_MUTATION_ENABLED",
  "JIUWENSWARM_LIVE_VOICE_CRITICAL_INPUT_ENABLED",
  "JIUWENSWARM_LIVE_VOICE_DEDICATED_MEDIA_ENABLED",
  "JIUWENSWARM_LIVE_VOICE_END_OF_TURN_ENABLED",
  "JIUWENSWARM_LIVE_VOICE_WEB_ALPHA_CREDENTIAL_ENABLED",
  "LIVE_VOICE_FORMAL_BATCH_SPEECH_ENABLED",
  "LIVE_VOICE_FORMAL_STREAMING_SPEECH_ENABLED",
];

function readEnv(name) {
  return Object.fromEntries(
    readFileSync(join(frontendRoot, name), "utf8")
      .split(/\r?\n/u)
      .map((line) => line.trim())
      .filter((line) => line.length > 0 && !line.startsWith("#"))
      .map((line) => {
        const separator = line.indexOf("=");
        assert.notEqual(separator, -1, `malformed environment line: ${line}`);
        return [line.slice(0, separator), line.slice(separator + 1)];
      }),
  );
}

test("ordinary production is flag-off and the explicit Live Voice profile is flag-on", () => {
  const production = readEnv(".env.production");
  const liveVoice = readEnv(".env.live-voice");

  for (const flag of formalLiveVoiceFlags) {
    assert.equal(production[flag], "false", `${flag} must be off in production`);
    assert.equal(liveVoice[flag], "true", `${flag} must be on in live-voice mode`);
  }
  for (const legacyFlag of [
    "VITE_FEATURE_LIVE_VOICE_TASK_DEMO",
    "VITE_FEATURE_LIVE_VOICE_STREAMING_SPEECH",
  ]) {
    assert.equal(production[legacyFlag], undefined);
    assert.equal(liveVoice[legacyFlag], undefined);
  }
  for (const deviceSpecificFlag of [
    "VITE_LIVE_VOICE_LOCAL_BARGE_IN_PAUSE",
    "VITE_LIVE_VOICE_LOCAL_BARGE_IN_PROFILE",
  ]) {
    assert.equal(production[deviceSpecificFlag], undefined);
    assert.equal(liveVoice[deviceSpecificFlag], undefined);
  }
});

test("the controlled launcher selects local barge-in only for the explicit verified headset profile", () => {
  const launcher = readFileSync(
    join(repoRoot, "scripts", "live_voice", "start_hands_free_demo.ps1"),
    "utf8",
  );
  assert.match(launcher, /ValidateSet\('off', 'verified-headset-aec-v1'\)/u);
  assert.match(launcher, /\[string\]\$LocalBargeInProfile = 'off'/u);
  assert.match(launcher, /RuntimeProfile -ne 'formal-web-validation'/u);
  assert.match(launcher, /VITE_LIVE_VOICE_LOCAL_BARGE_IN_PROFILE/u);
  assert.match(launcher, /verified_headset_aec_v1/u);
  assert.match(launcher, /VITE_LIVE_VOICE_LOCAL_BARGE_IN_PAUSE/u);
  assert.match(launcher, /local_barge_in_profile\s+=\s+\$LocalBargeInProfile/u);
});

test("the controlled launcher builds the explicit profile and owns Demo-only runtime exceptions", () => {
  const packageJson = JSON.parse(
    readFileSync(join(frontendRoot, "package.json"), "utf8"),
  );
  const launcher = readFileSync(
    join(repoRoot, "scripts", "live_voice", "start_hands_free_demo.ps1"),
    "utf8",
  );
  const formalWebLauncher = readFileSync(
    join(repoRoot, "scripts", "live_voice", "start_formal_web_validation.cmd"),
    "utf8",
  );

  assert.equal(packageJson.scripts.build, "tsc && vite build");
  assert.equal(
    packageJson.scripts["build:live-voice"],
    "tsc && vite build --mode live-voice",
  );
  assert.match(launcher, /\.env\.live-voice/u);
  assert.match(launcher, /run build:live-voice/u);
  assert.match(launcher, /start_services debug --skip-build/u);
  assert.match(
    launcher,
    /ValidateSet\('hands-free-demo', 'formal-web-validation'\)/u,
  );
  assert.match(
    formalWebLauncher,
    /-RuntimeProfile formal-web-validation -RestartExisting/u,
  );
  for (const portParameter of [
    "AgentServerPort",
    "WebPort",
    "GatewayPort",
    "FrontendPort",
  ]) {
    assert.match(
      launcher,
      new RegExp(`\\[int\\]\\$${portParameter}\\b`, "u"),
      `${portParameter} must be an explicit controlled-launcher parameter`,
    );
  }
  assert.match(
    launcher,
    /AGENT_SERVER_PORT\s*=\s*\$AgentServerPort/u,
  );
  assert.match(launcher, /WEB_PORT\s*=\s*\$WebPort/u);
  assert.match(launcher, /GATEWAY_PORT\s*=\s*\$GatewayPort/u);
  assert.match(
    launcher,
    /ExpectedPorts\.Values \| Select-Object -Unique/u,
  );
  assert.match(
    launcher,
    /ValidateSet\('cascade', 'openai-realtime-native'\)/u,
  );
  assert.match(
    launcher,
    /LIVE_VOICE_INTERACTION_ENGINE\s+=\s+\$InteractionEngine/u,
  );
  assert.match(
    launcher,
    /LIVE_VOICE_NATIVE_REALTIME_MODEL\s+=\s+\$NativeRealtimeModel/u,
  );
  assert.match(
    launcher,
    /interaction_engine\s+=\s+\$InteractionEngine/u,
  );
  assert.match(
    launcher,
    /JIUWENSWARM_LIVE_VOICE_RUNTIME_PROFILE\s*=\s*\$RuntimeProfile/u,
  );
  assert.match(launcher, /live-voice\.direct-project-code\.d2\.v2/u);
  assert.match(launcher, /executor_profile\s+=\s+\$ExecutorProfile/u);
  assert.match(launcher, /requiredRuntimeFlags/u);
  assert.match(launcher, /live_voice_runtime_contract\.json/u);
  assert.match(
    launcher,
    /ValidateSet\('off', 'verified-headset-aec-v1'\)/u,
  );
  assert.match(
    launcher,
    /VITE_LIVE_VOICE_LOCAL_BARGE_IN_PROFILE[\s\S]*verified_headset_aec_v1/u,
  );
  assert.match(
    launcher,
    /VITE_LIVE_VOICE_LOCAL_BARGE_IN_PAUSE[\s\S]*\$localBargeInEnabled/u,
  );
  assert.match(
    launcher,
    /local_barge_in_profile\s+=\s+\$LocalBargeInProfile/u,
  );
  assert.match(launcher, /schema_version\s+=\s+2/u);
  assert.match(launcher, /local_barge_in_profile\s+=\s+\$localBargeInBuildProfile/u);
  assert.match(launcher, /local_barge_in_pause\s+=\s+\$localBargeInEnabled/u);
  assert.match(
    launcher,
    /PSObject\.Properties\['local_barge_in_profile'\][\s\S]*savedLocalBargeInProperty\.Value/u,
  );
  assert.match(launcher, /Formal Web 验证要求干净源码/u);
  assert.match(launcher, /Wait-HttpResponse/u);
  assert.match(launcher, /external_channels/u);
  assert.match(launcher, /formal_web_runtime_probe\.py/u);
  assert.match(launcher, /gateway_claim_policy/u);
  assert.match(
    launcher,
    /bundleUrl = "http:\/\/127\.0\.0\.1:\$FrontendPort\$\{assetPath\}/u,
  );
  for (const flag of controlledRuntimeFlags) {
    assert.ok(
      launcher.split(flag).length - 1 >= 2,
      `${flag} must be both configured and independently required`,
    );
  }
  assert.match(
    launcher,
    /Remove-Item -LiteralPath "Env:\\\$frontendOverride"/u,
  );
  assert.doesNotMatch(
    launcher,
    /JIUWENSWARM_LIVE_VOICE_PRODUCT_DEMO_POLICY_BYPASS_ENABLED\s*=\s*'1'/u,
  );
  assert.doesNotMatch(
    launcher,
    /JIUWENSWARM_LIVE_VOICE_DEMO_ADJUSTMENT_CHECKPOINT_ENABLED\s*=\s*'1'/u,
  );
  assert.doesNotMatch(
    readFileSync(join(frontendRoot, ".env.live-voice"), "utf8"),
    /JIUWENSWARM_LIVE_VOICE_(?:PRODUCT_DEMO_POLICY_BYPASS|DEMO_ADJUSTMENT_CHECKPOINT)_ENABLED/u,
  );
});
