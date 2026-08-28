#!/usr/bin/env bash
# Run the jiuwenswarm test suite inside a rootless podman container.  [local]
#
#   containers/run-tests.sh [options] [-- pytest args...]
#
# Options:
#   -w, --worktree PATH   jiuwenswarm worktree to test   (default: repo root)
#       --ac PATH         agent-core worktree; openjiuwen is built from it
#       --ac-ref REF      agent-core git ref to install openjiuwen from
#                         (--ac and --ac-ref are mutually exclusive; with
#                          neither, openjiuwen is whatever pyproject resolves)
#       --ci-pins         pin pytest 9.0.3 / pluggy 1.6.0 to match CI
#       --python VERSION  interpreter minor version         (default: 3.11)
#       --refresh-venv    discard the cached venv volume first
#       --no-network      run with no network (cold venv builds need network)
#       --venv-tag TAG    extra venv-key component, for a private volume
#       --build           (re)build the image before running
#       --shell           drop into a shell instead of running pytest
#   -h, --help
set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO=$(cd "$HERE/.." && pwd)

WORKTREE=$REPO
AC_PATH=""; AC_REF=""; CI_PINS=0; PYVER=3.11
REFRESH=0; NETWORK=1; VENV_TAG=""; DO_BUILD=0; SHELL_MODE=0
IMAGE=${JWS_TEST_IMAGE:-localhost/jws-test:latest}

die() { printf 'run-tests.sh: %s\n' "$*" >&2; exit 2; }

while [ $# -gt 0 ]; do
    case "$1" in
        -w|--worktree) WORKTREE=$2; shift 2 ;;
        --ac)          AC_PATH=$2;  shift 2 ;;
        --ac-ref)      AC_REF=$2;   shift 2 ;;
        --ci-pins)     CI_PINS=1;   shift ;;
        --python)      PYVER=$2;    shift 2 ;;
        --refresh-venv) REFRESH=1;  shift ;;
        --no-network)  NETWORK=0;   shift ;;
        --venv-tag)    VENV_TAG=$2; shift 2 ;;
        --build)       DO_BUILD=1;  shift ;;
        --shell)       SHELL_MODE=1; shift ;;
        -h|--help)     sed -n '2,25p' "$0"; exit 0 ;;
        --)            shift; break ;;
        *)             break ;;
    esac
done

[ -n "$AC_PATH" ] && [ -n "$AC_REF" ] && die "--ac and --ac-ref are mutually exclusive"
WORKTREE=$(cd "$WORKTREE" && pwd) || die "no such worktree"
[ -f "$WORKTREE/pyproject.toml" ] || die "$WORKTREE has no pyproject.toml"
if [ -n "$AC_PATH" ]; then
    AC_PATH=$(cd "$AC_PATH" && pwd) || die "no such agent-core worktree"
    [ -f "$AC_PATH/pyproject.toml" ] || die "$AC_PATH has no pyproject.toml"
fi

if [ "$DO_BUILD" = 1 ] || ! podman image exists "$IMAGE"; then
    printf '[runner] building %s (python %s)\n' "$IMAGE" "$PYVER" >&2
    podman build --build-arg "PYTHON_VERSION=$PYVER" -t "$IMAGE" "$HERE"
fi

# --- openjiuwen identity ----------------------------------------------------
# openjiuwen is 0.1.17 both on upstream develop and on our integration branch,
# so the version number cannot tell them apart.  The identity is therefore the
# commit plus a hash of any uncommitted change, because openjiuwen is installed
# from the tree as a built wheel and a dirty tree yields different bytes.
if [ -n "$AC_PATH" ]; then
    ac_head=$(git -C "$AC_PATH" rev-parse HEAD 2>/dev/null || echo nogit)
    ac_dirty=$( { git -C "$AC_PATH" diff HEAD 2>/dev/null || true
                  git -C "$AC_PATH" ls-files --others --exclude-standard 2>/dev/null || true
                } | sha256sum | cut -c1-12)
    OJ_ID="local:${ac_head:0:12}:$ac_dirty"
elif [ -n "$AC_REF" ]; then
    OJ_ID="git:$AC_REF"
else
    # Identifies the declared requirement, not the commit it resolves to: a
    # branch requirement such as @develop can move between runs without the
    # declaration changing.  Use --ac-ref when a run must be reproducible.
    OJ_REQ=$(python3 - "$WORKTREE/pyproject.toml" <<PYEOF
import sys, tomllib
with open(sys.argv[1], "rb") as fh:
    data = tomllib.load(fh)
for dep in data["project"]["dependencies"]:
    if dep.split("[")[0].split("@")[0].strip().lower() == "openjiuwen":
        print(dep)
        break
PYEOF
)
    OJ_ID="pyproject:$(printf '%s' "$OJ_REQ" | sha256sum | cut -c1-12)"
fi

# --- venv cache key ---------------------------------------------------------
# Everything that changes the resolved dependency closure, and nothing that
# does not.  The worktree path is deliberately absent: the source is mounted at
# a fixed path, so one venv serves every branch whose declaration is identical.
# openjiuwen is NOT in this key — it is reconciled per run against OJ_ID.
# Not the image ID: that changes whenever entrypoint.sh does, which cannot
# affect the closure.  The label lists the image properties that can, and the
# base digest catches a moved upstream python:*-slim-bookworm.
VENV_INPUTS=$(podman image inspect --format '{{index .Config.Labels "jws.venv_inputs"}}' "$IMAGE")
BASE_DIGEST=$(podman image inspect --format '{{.Digest}}' \
    "docker.io/library/python:$PYVER-slim-bookworm" 2>/dev/null || echo unpinned)
VENV_KEY=$(printf '%s|%s|%s|%s|%s|%s|%s' \
    "$VENV_INPUTS" "$BASE_DIGEST" "$PYVER" "test" "$CI_PINS" "$VENV_TAG" \
    "$(sha256sum "$WORKTREE/pyproject.toml" | cut -d' ' -f1)" \
    | sha256sum | cut -c1-12)
VOLUME="jws-venv-$VENV_KEY"

if [ "$REFRESH" = 1 ]; then
    printf '[runner] removing volume %s\n' "$VOLUME" >&2
    podman volume rm -f "$VOLUME" >/dev/null 2>&1 || true
fi

# --- mounts -----------------------------------------------------------------
# The host ~/.jiuwenswarm is never mounted.  That is the whole isolation
# claim: the operator config is unreachable, not merely unreferenced.
MOUNTS=(-v "$WORKTREE:/src/jws" -v "$VOLUME:/venv" -v "jws-cache:/cache")

# A linked worktree's .git is a file pointing at the main repo's gitdir, so
# that path has to resolve inside the container or every git call fails.  It is
# mounted read-only, and the worktree is mounted a second time at its own host
# path so git's stored absolute paths agree with what it finds.
if [ -f "$WORKTREE/.git" ]; then
    common=$(git -C "$WORKTREE" rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)
    if [ -n "$common" ]; then
        MOUNTS+=(-v "$common:$common:ro" -v "$WORKTREE:$WORKTREE")
    fi
fi
[ -n "$AC_PATH" ] && MOUNTS+=(-v "$AC_PATH:/src/ac:ro")

NET=(); [ "$NETWORK" = 0 ] && NET=(--network none)

if [ "$SHELL_MODE" = 1 ]; then
    CMD=(bash)
elif [ $# -gt 0 ]; then
    CMD=("$@")
else
    CMD=(pytest -p no:cacheprovider tests/unit_tests)
fi


TTY=(); [ -t 0 ] && [ -t 1 ] && TTY=(-t)

exec podman run --rm "${TTY[@]}" \
    "${MOUNTS[@]}" "${NET[@]}" \
    -e "JWS_VENV_KEY=$VENV_KEY" \
    -e "JWS_OJ_ID=$OJ_ID" \
    -e "JWS_AC_PATH=$( [ -n "$AC_PATH" ] && echo /src/ac )" \
    -e "JWS_AC_REF=$AC_REF" \
    -e "JWS_CI_PINS=$CI_PINS" \
    -e "JWS_SHOW_VERSIONS=${JWS_SHOW_VERSIONS:-0}" \
    "$IMAGE" "${CMD[@]}"
