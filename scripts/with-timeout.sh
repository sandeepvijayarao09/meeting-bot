#!/usr/bin/env bash
# with_timeout — run a command under a deadline. Sourced, never executed.
#
# This exists because scripts/preflight-release.sh hung forever on exactly the
# bundle it most needs to audit: the app out of a freshly downloaded DMG carries
# com.apple.quarantine, and Gatekeeper blocks the nested, ad-hoc-signed sidecar
# at exec time. The invocation never returns, no output is printed, and the gate
# that should have reported the defect reports nothing at all. An unbounded
# external call in a release gate is a silent failure mode.
#
# macOS has no `timeout` — it is GNU coreutils, which a release machine has no
# reason to carry — so the deadline is implemented with a background job and a
# poll loop rather than making `brew install coreutils` a prerequisite.
#
#   source "$(dirname "${BASH_SOURCE[0]}")/with-timeout.sh"
#   with_timeout SECONDS COMMAND [ARG...]
#
# Returns COMMAND's own exit status, or $TIMEOUT_STATUS if it was still running
# after SECONDS. stdout and stderr pass through untouched, so the result can be
# captured the same way the unbounded call was.

# 124 is the status GNU timeout reports, and no command we bound returns it.
TIMEOUT_STATUS=124

with_timeout() {
  local limit="$1"
  shift

  # Backgrounding a simple command execs it directly, so $! is the command
  # itself — killing it kills the process that is actually blocked, not a
  # wrapper subshell that would leave the real one orphaned and still holding
  # the pipe this function's caller is reading from.
  "$@" &
  local pid=$!

  local waited=0
  local ticks=$((limit * 10))
  while [ "$waited" -lt "$ticks" ]; do
    kill -0 "$pid" 2>/dev/null || { wait "$pid"; return $?; }
    sleep 0.1
    waited=$((waited + 1))
  done

  # One last look: bash reaps background children asynchronously, so a command
  # that finished during the final tick may not have been collected yet.
  kill -0 "$pid" 2>/dev/null || { wait "$pid"; return $?; }

  # The shell announces a killed job ("Terminated: 15") on its own stderr, not
  # the job's, so redirecting `kill` or `wait` does not catch it; mute this
  # shell until the job is reaped, or the notice lands mid-report. The command
  # already holds the real stderr, so its own output is unaffected.
  exec 3>&2 2>/dev/null
  kill -TERM "$pid" 2>/dev/null
  sleep 0.5
  kill -KILL "$pid" 2>/dev/null
  wait "$pid"
  exec 2>&3 3>&-
  return "$TIMEOUT_STATUS"
}
