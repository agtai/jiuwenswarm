#!/usr/bin/env bash
# Run-time provisioning for the test container.  [local]
#
# Builds the venv on first use into the /venv volume, then reconciles which
# openjiuwen is installed against the identity the runner computed.  Both steps
# are no-ops on a warm run.
set -euo pipefail

log() { printf '[container] %s\n' "$*" >&2; }

JWS_SRC=${JWS_SRC:-/src/jws}
VENV=${VIRTUAL_ENV:-/venv}
VENV_KEY=${JWS_VENV_KEY:-unkeyed}
OJ_ID=${JWS_OJ_ID:-resolved-from-pyproject}
AC_PATH=${JWS_AC_PATH:-}
AC_REF=${JWS_AC_REF:-}
CI_PINS=${JWS_CI_PINS:-0}

mkdir -p "$(dirname "$VENV")" /cache/pip /cache/npm
exec 9>"/tmp/.venv-provision.lock"
flock 9

# --- 1. the venv itself -----------------------------------------------------
# Keyed by the runner on the dependency-declaration inputs, so a venv is only
# ever reused for an identical declared closure.  The stamp is re-checked here
# so a hand-mounted or hand-edited volume cannot masquerade as the right one.
if [ -x "$VENV/bin/python" ] && [ "$(cat "$VENV/.venv-key" 2>/dev/null || true)" = "$VENV_KEY" ]; then
    log "venv hit ($VENV_KEY)"
else
    if [ -x "$VENV/bin/python" ]; then
        log "venv key mismatch: have '$(cat "$VENV/.venv-key" 2>/dev/null || echo none)', want '$VENV_KEY' — rebuilding"
        find "$VENV" -mindepth 1 -maxdepth 1 -exec rm -rf {} +
    else
        log "venv cold build ($VENV_KEY)"
    fi
    python3 -m venv "$VENV"
    "$VENV/bin/pip" install -q -U pip wheel
    # The [test] extra is load-bearing: it pins a2a-sdk[http-server]==1.0.0.
    # Without it a2a-sdk resolves transitively and drifts to 1.1.2.
    "$VENV/bin/pip" install -e "$JWS_SRC[test]"
    if [ "$CI_PINS" = "1" ]; then
        log "applying CI pins (pytest 9.0.3 / pluggy 1.6.0)"
        "$VENV/bin/pip" install -q "pytest==9.0.3" "pluggy==1.6.0"
    fi
    printf '%s' "$VENV_KEY" > "$VENV/.venv-key"
    rm -f "$VENV/.openjiuwen-stamp"
fi

# --- 2. which openjiuwen ----------------------------------------------------
# The venv volume is shared across openjiuwen variants on purpose: reinstalling
# one 6MB wheel takes seconds, rebuilding the ~900-package closure takes
# minutes.  Reuse is therefore never silent — the stamp is compared on every
# run and a mismatch forces a reinstall before any test is collected.
current_stamp=$(cat "$VENV/.openjiuwen-stamp" 2>/dev/null || true)
if [ "$current_stamp" = "$OJ_ID" ]; then
    log "openjiuwen hit ($OJ_ID)"
else
    log "openjiuwen change: '$current_stamp' -> '$OJ_ID'"
    if [ -n "$AC_PATH" ]; then
        # The agent-core tree is mounted read-only so a test run can never
        # modify it, but a setuptools build writes openjiuwen.egg-info into the
        # source directory.  Build from a throwaway copy instead of loosening
        # the mount: the shared checkout stays pristine either way.
        rm -rf /tmp/ac-build && mkdir -p /tmp/ac-build
        tar -C "$AC_PATH" --exclude=.git --exclude=node_modules -cf - . \
            | tar -C /tmp/ac-build -xf -
        "$VENV/bin/pip" install -q --no-deps --force-reinstall /tmp/ac-build
        rm -rf /tmp/ac-build
    elif [ -n "$AC_REF" ]; then
        "$VENV/bin/pip" install -q --no-deps --force-reinstall \
            "openjiuwen @ git+https://gitcode.com/openJiuwen/agent-core.git@${AC_REF}"
    else
        # No override.  The venv may still hold an openjiuwen left by a
        # previous --ac/--ac-ref run, so the declared requirement has to be
        # reinstalled rather than assumed; otherwise switching back to the
        # stock combination would silently keep the custom build.
        req=$("$VENV/bin/python" - "$JWS_SRC/pyproject.toml" <<PYEOF
import sys, tomllib
with open(sys.argv[1], "rb") as fh:
    data = tomllib.load(fh)
for dep in data["project"]["dependencies"]:
    if dep.split("[")[0].split("@")[0].strip().lower() == "openjiuwen":
        print(dep)
        break
PYEOF
)
        if [ -z "$req" ]; then
            log "FATAL: pyproject declares no openjiuwen requirement"
            exit 3
        fi
        log "restoring the declared requirement: $req"
        "$VENV/bin/pip" install -q --no-deps --force-reinstall "$req"
    fi
    # --no-deps is only safe while the override declares no dependency the
    # resolve did not already install.  pip check turns that assumption into a
    # verified precondition instead of a silent ImportError mid-suite.
    if ! "$VENV/bin/pip" check; then
        log "FATAL: dependency check failed after installing openjiuwen."
        log "The agent-core override likely declares a dependency the"
        log "jiuwenswarm resolve did not install.  Re-run with --refresh-venv."
        exit 3
    fi
    printf '%s' "$OJ_ID" > "$VENV/.openjiuwen-stamp"
fi

flock -u 9
exec 9>&-

if [ "${JWS_SHOW_VERSIONS:-0}" = "1" ]; then
    "$VENV/bin/python" - <<'PY' >&2
import importlib.metadata as m
for n in ("pytest", "pluggy", "a2a-sdk", "openjiuwen", "workswarm"):
    try:
        print(f"[container] {n}=={m.version(n)}")
    except Exception as exc:
        print(f"[container] {n}: {exc}")
PY
fi

cd "$JWS_SRC"
exec "$@"
