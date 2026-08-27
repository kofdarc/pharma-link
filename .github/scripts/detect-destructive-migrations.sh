#!/usr/bin/env bash
set -euo pipefail

base_sha="${1:?base SHA is required}"
head_sha="${2:?head SHA is required}"
output_file="${3:-migration-safety.json}"

mapfile -t migration_files < <(
  git diff --diff-filter=A --name-only "$base_sha" "$head_sha" -- \
    'apps/api/apps/*/migrations/*.py'
)

destructive=false
matches=""
if ((${#migration_files[@]})); then
  matches="$(grep -En 'migrations\.(RemoveField|DeleteModel|AlterField)\(' "${migration_files[@]}" || true)"
  if [[ -n "$matches" ]]; then
    destructive=true
  fi
fi

jq -n \
  --argjson destructive "$destructive" \
  --arg base "$base_sha" \
  --arg head "$head_sha" \
  --arg matches "$matches" \
  --argjson files "$(printf '%s\n' "${migration_files[@]:-}" | jq -Rsc 'split("\n") | map(select(length > 0))')" \
  '{destructive: $destructive, base: $base, head: $head, migration_files: $files, matches: $matches}' \
  > "$output_file"

echo "destructive=$destructive" >> "$GITHUB_OUTPUT"
if [[ -n "$matches" ]]; then
  {
    echo '### Potentially destructive migration operations'
    echo '```'
    echo "$matches"
    echo '```'
  } >> "$GITHUB_STEP_SUMMARY"
fi
