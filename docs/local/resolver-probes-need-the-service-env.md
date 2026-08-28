# Driving a config resolver from a bare shell invents defects

Recorded 2026-08-27 after this produced a false finding that survived two
retellings before it was checked. Relevant to any work that probes config
resolution in place -- `scopes` especially, since its whole subject is resolving
a value per caller.

## The technique, and why it is otherwise good

Importing a resolver from the deployed venv and calling it on the live config
settles questions that log-reading cannot. It confirmed the cron delivery guard,
the circuit-breaker detectors and the `render_tables` modes on the same day this
went wrong. Nothing below argues against the technique.

## The trap

The service reads `~/.jiuwenswarm/config/.env` at startup. **A shell does not.**
So a resolver driven from a bare shell sees `${VAR}` placeholders that never
expand, and every code path guarding on "is this value known" takes the failure
branch.

Measured, same command, same config, one difference:

```
MODEL_NAME unset      get_model_names() -> ['Gemma4-26B']
MODEL_NAME loaded     get_model_names() -> ['deepseek-v4-flash-0731', 'Gemma4-26B']
```

On the first, a scope's `agent.model_name: deepseek-v4-flash-0731` for one channel is
rejected as "not one of the models configured" and dropped. That was reported as
a real defect -- a channel supposedly unable to pin itself to the deployment's own
default model, with a config comment describing an A/B test that had never run.
None of it was true. `get_model_names` is upstream's code, it calls
`resolve_env_vars` correctly, and the override had been working the whole time.

## What made it convincing, and the check that breaks the spell

The false finding came with warnings in the real log file, at plausible
timestamps, naming real channels. They were **the probe's own output**: the
harness imports the deployed `jiuwenswarm` logger, which owns file handlers on
`~/.jiuwenswarm/agent/.logs/`, so anything it logs lands in the same file the
service writes to and is indistinguishable by eye.

**Timestamp every warning against the service's start time before believing it.**

```
service started        12:20:37   -> its startup warnings cluster at 12:20:5x
the "finding" warnings 15:31+     -> the probe's own runs
```

Here the service's only genuine warning of that shape named a deliberately fake
test fixture, which was the correct behaviour, and every warning naming a real
channel post-dated the probes by three hours.

## Do this instead

Load the environment the service loads, in the same command:

```bash
cd /home/jiuwenswarm/.jiuwenswarm
set -a; . /home/jiuwenswarm/.jiuwenswarm/config/.env; set +a
/home/jiuwenswarm/venvs/<current>/bin/python - <<'PY'
...
PY
```

and, when a probe's result depends on a value that could be a placeholder, print
the resolved value beside the verdict rather than the verdict alone. A line
reading `MODEL_NAME visible to python: deepseek-v4-flash-0731` next to the answer
would have caught this before it was ever reported.

Also: prefer a before/after comparison over a single reading. A connector
config-key removal the same day was proven a no-op by resolving every channel's
triggers on both sides and diffing -- a shape that cannot produce
this error, because a missing environment biases both readings equally.

## The general rule

An isolated run can hide a real coupling to ambient machine state, and it can
also **invent** a failure by removing state the service has. Both directions cost
a false conclusion. Cross-check any in-process probe once against the real
environment before reporting what it found.

See [[config-template-prunes-unlisted-keys]] for the other way this config is
easy to reason about wrongly.
