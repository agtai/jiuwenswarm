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
});

test("the controlled launcher builds the explicit profile and owns Demo-only runtime exceptions", () => {
  const packageJson = JSON.parse(
    readFileSync(join(frontendRoot, "package.json"), "utf8"),
  );
  const launcher = readFileSync(
    join(repoRoot, "scripts", "live_voice", "start_hands_free_demo.ps1"),
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
    /Remove-Item -LiteralPath "Env:\\\$frontendOverride"/u,
  );
  assert.match(
    launcher,
    /JIUWENSWARM_LIVE_VOICE_PRODUCT_DEMO_POLICY_BYPASS_ENABLED\s*=\s*'1'/u,
  );
  assert.match(
    launcher,
    /JIUWENSWARM_LIVE_VOICE_DEMO_ADJUSTMENT_CHECKPOINT_ENABLED\s*=\s*'1'/u,
  );
  assert.doesNotMatch(
    readFileSync(join(frontendRoot, ".env.live-voice"), "utf8"),
    /JIUWENSWARM_LIVE_VOICE_(?:PRODUCT_DEMO_POLICY_BYPASS|DEMO_ADJUSTMENT_CHECKPOINT)_ENABLED/u,
  );
});
