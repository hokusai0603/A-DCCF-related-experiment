#!/usr/bin/env bash
# Regenerate backup/<date>/changes.diff: backed-up file vs current infra working copy,
# plus files that did not exist at backup time (shown as new).
set -u
D=${1:-2026-11-10}; B=$HOME/Research-data-collection/backup/$D; I=$HOME/free5gc-NWDAF/5G_Infrastructure
NEW_FILES="config/UERAN/ue-s1-scale.yaml config/UERAN/ue-s2-scale.yaml"
{
  cd "$B/infra" && find . -type f | sort | while read -r f; do f=${f#./}; diff -u "a/$f" "b/$f" >/dev/null 2>&1; diff -u --label "a/$f" --label "b/$f" "$B/infra/$f" "$I/$f"; done
  for f in $NEW_FILES; do [ -f "$I/$f" ] && diff -u --label /dev/null --label "b/$f" /dev/null "$I/$f"; done
} > "$B/changes.diff"
echo "$B/changes.diff: $(grep -c '^+++ ' "$B/changes.diff") files changed"
