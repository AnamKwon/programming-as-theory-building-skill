#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  ./run_skill_codegen_experiment.sh [prompt-file]

Runs the same Claude Code code-generation prompt repeatedly in three default arms:
  skills_off:   disables managed SKILL.md files by renaming them
  karpathy_only: enables only the compact comparison-guidelines SKILL.md
  theory_only:  enables only the programming-as-theory-building SKILL.md
Environment:
  REPEATS=10
  OUTPUT_ROOT=.skill-codegen-runs
  RUN_WORK_ROOT=$TMPDIR
  CLAUDE_BIN=claude
  MANAGED_SKILL_DIRS=$HOME/.claude/skills
  KARPATHY_SKILL=karpathy-guidelines
  THEORY_SKILL=programming-as-theory-building
  ARMS="skills_off karpathy_only theory_only"
  BARE=1
  DISABLE_MCP=1
  MCP_CONFIG_JSON='{"mcpServers":{}}'
  MODEL=sonnet
  MAX_BUDGET_USD=1.00
  Set BARE=0 only if your Claude authentication cannot run in bare mode.

Output:
  Results are written under OUTPUT_ROOT/<timestamp>/.
  Each run's stdout file contains only Claude's printed result.
  Each Claude process starts in a fresh empty temp workspace for that run.
  The temp workspace is moved into the result folder after the run.
  If you pass a prompt file, keep it self-contained to avoid referencing existing code.
  Managed SKILL.md files are renamed globally during the experiment and restored on normal exit, error, INT, or TERM.
  Do not run other Claude sessions while this script is running.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

ORIGINAL_CWD="$(pwd)"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
PROMPT_FILE="${1:-${PROMPT_FILE:-}}"
if [[ -n "$PROMPT_FILE" && "$PROMPT_FILE" != /* ]]; then
  PROMPT_FILE="$ORIGINAL_CWD/$PROMPT_FILE"
fi

cd "$SCRIPT_DIR"

REPEATS="${REPEATS:-10}"
OUTPUT_ROOT="${OUTPUT_ROOT:-.skill-codegen-runs}"
RUN_WORK_ROOT="${RUN_WORK_ROOT:-${TMPDIR:-/tmp}}"
CLAUDE_BIN="${CLAUDE_BIN:-claude}"
MANAGED_SKILL_DIRS="${MANAGED_SKILL_DIRS:-$HOME/.claude/skills}"
CLAUDE_GLOBAL_SKILL_DIR="${CLAUDE_GLOBAL_SKILL_DIR:-$HOME/.claude/skills}"
KARPATHY_SKILL="${KARPATHY_SKILL:-karpathy-guidelines}"
THEORY_SKILL="${THEORY_SKILL:-programming-as-theory-building}"
ARMS="${ARMS:-skills_off karpathy_only theory_only}"
BARE="${BARE:-1}"
DISABLE_MCP="${DISABLE_MCP:-1}"
if [[ -z "${MCP_CONFIG_JSON+x}" ]]; then
  MCP_CONFIG_JSON='{"mcpServers":{}}'
fi
MODEL="${MODEL:-}"
MAX_BUDGET_USD="${MAX_BUDGET_USD:-}"
KARPATHY_SKILL_FILE=""
THEORY_SKILL_FILE=""
ACTIVE_RUN_WORK_DIR=""
SKILL_DISABLE_SUFFIX=".disabled-by-skill-codegen"
MANAGED_SKILL_FILES=()
RENAMED_SKILL_ORIGINALS=()
RENAMED_SKILL_DISABLED=()

if [[ "$OUTPUT_ROOT" != /* ]]; then
  OUTPUT_ROOT="$SCRIPT_DIR/$OUTPUT_ROOT"
fi
if [[ "$RUN_WORK_ROOT" != /* ]]; then
  RUN_WORK_ROOT="${TMPDIR:-/tmp}/$RUN_WORK_ROOT"
fi

error() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}

cleanup_active_run_work_dir() {
  if [[ -n "${ACTIVE_RUN_WORK_DIR:-}" && -d "$ACTIVE_RUN_WORK_DIR" ]]; then
    rm -rf "$ACTIVE_RUN_WORK_DIR" || true
  fi
}

restore_skill_files() {
  local i
  local original
  local disabled

  for i in "${!RENAMED_SKILL_ORIGINALS[@]}"; do
    original="${RENAMED_SKILL_ORIGINALS[$i]}"
    disabled="${RENAMED_SKILL_DISABLED[$i]}"
    if [[ -f "$disabled" && ! -e "$original" ]]; then
      mv "$disabled" "$original" || true
    fi
  done
}

cleanup_all() {
  cleanup_active_run_work_dir
  restore_skill_files
}

trap cleanup_all EXIT
trap 'cleanup_all; exit 130' INT
trap 'cleanup_all; exit 143' TERM

is_positive_integer() {
  [[ "$1" =~ ^[1-9][0-9]*$ ]]
}

is_false() {
  case "$1" in
    0|false|FALSE|no|NO|off|OFF)
      return 0
      ;;
    *)
      return 1
      ;;
  esac
}

canonicalize_path() {
  local path="$1"
  local parent="$path"
  local suffix=""

  while [[ ! -d "$parent" ]]; do
    suffix="/$(basename "$parent")$suffix"
    parent="$(dirname "$parent")"
  done

  local canonical_parent
  canonical_parent="$(cd "$parent" && pwd -P)" || return 1
  normalize_absolute_path "$canonical_parent$suffix"
}

normalize_absolute_path() {
  local path="$1"
  local old_ifs="$IFS"
  local parts=()
  local stack=()
  local part

  IFS='/'
  read -r -a parts <<< "$path"
  IFS="$old_ifs"

  for part in "${parts[@]}"; do
    case "$part" in
      ""|.)
        ;;
      ..)
        if [[ "${#stack[@]}" -gt 0 ]]; then
          stack=("${stack[@]:0:${#stack[@]}-1}")
        fi
        ;;
      *)
        stack+=("$part")
        ;;
    esac
  done

  local normalized=""
  for part in "${stack[@]}"; do
    normalized="$normalized/$part"
  done
  printf '%s\n' "${normalized:-/}"
}

path_contains_or_equals() {
  local root="$1"
  local path="$2"

  if [[ "$root" == "/" ]]; then
    return 0
  fi
  root="${root%/}"
  path="${path%/}"
  [[ "$path" == "$root" || "$path" == "$root"/* ]]
}

each_managed_skill_dir() {
  local dirs=()
  local old_ifs="$IFS"
  local dir

  IFS=':'
  read -r -a dirs <<< "$MANAGED_SKILL_DIRS"
  IFS="$old_ifs"

  for dir in "${dirs[@]}"; do
    [[ -n "$dir" ]] || continue
    if [[ "$dir" != /* ]]; then
      dir="$SCRIPT_DIR/$dir"
    fi
    printf '%s\n' "$dir"
  done
}

resolve_managed_skill_file() {
  local requested="$1"
  shift
  local candidate
  local dir

  for candidate in "$requested" "$@"; do
    while IFS= read -r dir; do
      if [[ -f "$dir/$candidate/SKILL.md" ]]; then
        printf '%s\n' "$dir/$candidate/SKILL.md"
        return 0
      fi
    done < <(each_managed_skill_dir)
  done

  return 1
}

collect_managed_skill_files() {
  local dir
  local skill_file

  MANAGED_SKILL_FILES=()
  while IFS= read -r dir; do
    [[ -d "$dir" ]] || continue
    while IFS= read -r -d '' skill_file; do
      MANAGED_SKILL_FILES+=("$skill_file")
    done < <(find "$dir" -mindepth 2 -maxdepth 2 -type f -name SKILL.md -print0)
  done < <(each_managed_skill_dir)
}

recover_stale_disabled_skill_files() {
  local dir
  local disabled_file
  local original_file

  while IFS= read -r dir; do
    [[ -d "$dir" ]] || continue
    while IFS= read -r -d '' disabled_file; do
      original_file="${disabled_file%%.disabled-by-skill-codegen*}"
      if [[ -f "$original_file" ]]; then
        continue
      fi
      if ! mv "$disabled_file" "$original_file"; then
        printf 'warning: could not recover stale disabled skill file: %s\n' "$disabled_file" >&2
      fi
    done < <(find "$dir" -mindepth 2 -maxdepth 2 -type f -name 'SKILL.md.disabled-by-skill-codegen*' -print0)
  done < <(each_managed_skill_dir)
}

remember_renamed_skill_file() {
  local original="$1"
  local disabled="$2"
  local i

  for i in "${!RENAMED_SKILL_ORIGINALS[@]}"; do
    if [[ "${RENAMED_SKILL_ORIGINALS[$i]}" == "$original" ]]; then
      return
    fi
  done

  RENAMED_SKILL_ORIGINALS+=("$original")
  RENAMED_SKILL_DISABLED+=("$disabled")
}

set_skill_file_enabled() {
  local skill_file="$1"
  local enabled="$2"
  local disabled_file="$skill_file$SKILL_DISABLE_SUFFIX"

  if [[ "$enabled" == "1" ]]; then
    if [[ -f "$disabled_file" ]]; then
      if [[ -e "$skill_file" ]]; then
        error "cannot enable skill because both files exist: $skill_file and $disabled_file"
      fi
      mv "$disabled_file" "$skill_file"
    fi
  else
    if [[ -f "$skill_file" ]]; then
      if [[ -e "$disabled_file" ]]; then
        error "cannot disable skill because disabled file already exists: $disabled_file"
      fi
      mv "$skill_file" "$disabled_file"
      remember_renamed_skill_file "$skill_file" "$disabled_file"
    fi
  fi
}

set_skill_state_for_arm() {
  local arm="$1"
  local skill_file

  for skill_file in "${MANAGED_SKILL_FILES[@]}"; do
    set_skill_file_enabled "$skill_file" 0
  done

  case "$arm" in
    skills_off)
      ;;
    karpathy_only)
      set_skill_file_enabled "$KARPATHY_SKILL_FILE" 1
      ;;
    theory_only)
      set_skill_file_enabled "$THEORY_SKILL_FILE" 1
      ;;
    both)
      set_skill_file_enabled "$KARPATHY_SKILL_FILE" 1
      set_skill_file_enabled "$THEORY_SKILL_FILE" 1
      ;;
    *)
      error "unknown arm: $arm"
      ;;
  esac
}

check_inputs() {
  local resolved_claude_bin
  resolved_claude_bin="$(command -v "$CLAUDE_BIN")" || error "Claude binary not found: $CLAUDE_BIN"
  CLAUDE_BIN="$resolved_claude_bin"

  is_positive_integer "$REPEATS" || error "REPEATS must be a positive integer: $REPEATS"

  if [[ -n "$PROMPT_FILE" && ! -f "$PROMPT_FILE" ]]; then
    error "prompt file not found: $PROMPT_FILE"
  fi

  OUTPUT_ROOT="$(canonicalize_path "$OUTPUT_ROOT")" || error "cannot resolve OUTPUT_ROOT: $OUTPUT_ROOT"
  RUN_WORK_ROOT="$(canonicalize_path "$RUN_WORK_ROOT")" || error "cannot resolve RUN_WORK_ROOT: $RUN_WORK_ROOT"
  CLAUDE_GLOBAL_SKILL_DIR="$(canonicalize_path "$CLAUDE_GLOBAL_SKILL_DIR")" || {
    error "cannot resolve CLAUDE_GLOBAL_SKILL_DIR: $CLAUDE_GLOBAL_SKILL_DIR"
  }

  if path_contains_or_equals "$SCRIPT_DIR" "$RUN_WORK_ROOT"; then
    error "RUN_WORK_ROOT must not be inside the repo: $RUN_WORK_ROOT"
  fi
  if path_contains_or_equals "$OUTPUT_ROOT" "$RUN_WORK_ROOT"; then
    error "RUN_WORK_ROOT must not be inside OUTPUT_ROOT: $RUN_WORK_ROOT"
  fi
  if path_contains_or_equals "$RUN_WORK_ROOT" "$OUTPUT_ROOT"; then
    error "OUTPUT_ROOT must not be inside RUN_WORK_ROOT: $OUTPUT_ROOT"
  fi
  mkdir -p "$OUTPUT_ROOT" "$RUN_WORK_ROOT"
  recover_stale_disabled_skill_files
  collect_managed_skill_files
  local managed_skill_file
  local canonical_skill_file
  for managed_skill_file in "${MANAGED_SKILL_FILES[@]}"; do
    canonical_skill_file="$(canonicalize_path "$managed_skill_file")" || {
      error "cannot resolve managed skill file: $managed_skill_file"
    }
    if ! path_contains_or_equals "$CLAUDE_GLOBAL_SKILL_DIR" "$canonical_skill_file"; then
      error "managed skill is not discoverable from isolated workspaces: $managed_skill_file"
    fi
  done

  local needs_karpathy=0
  local needs_theory=0
  local arm
  for arm in $ARMS; do
    case "$arm" in
      skills_off)
        ;;
      karpathy_only)
        needs_karpathy=1
        ;;
      theory_only)
        needs_theory=1
        ;;
      both)
        needs_karpathy=1
        needs_theory=1
        ;;
      *)
        error "unknown arm: $arm"
        ;;
    esac
  done

  if [[ "$needs_karpathy" -eq 1 ]]; then
    KARPATHY_SKILL_FILE="$(resolve_managed_skill_file "$KARPATHY_SKILL" "andrej-karpathy" "karpathy-guidelines")" || {
      error "Comparison-guidelines skill not found in MANAGED_SKILL_DIRS: $MANAGED_SKILL_DIRS"
    }
  fi

  if [[ "$needs_theory" -eq 1 ]]; then
    THEORY_SKILL_FILE="$(resolve_managed_skill_file "$THEORY_SKILL")" || {
      error "theory-building skill not found in MANAGED_SKILL_DIRS: $MANAGED_SKILL_DIRS"
    }
  fi
}

emit_default_prompt() {
  cat <<'EOF'
You are in a fresh empty workspace.
Use any currently available Claude Code skills that apply to this code generation task.

Create a production-style Python service in the current working directory. Do not read parent directories or existing local projects.

Product:
Build a field-operations dispatch planner for a facilities team. The service receives work requests, normalizes them, assigns them to technicians, tracks lifecycle events, and exposes operational summaries.

Required files:
- pyproject.toml
- README.md
- src/dispatch_planner/__init__.py
- src/dispatch_planner/app.py
- tests/test_dispatch_planner.py

You may add extra modules and tests if they make the implementation easier to understand, but do not add layers or dependencies that are not needed for the requested behavior.

Functional requirements:
- Use FastAPI, Pydantic, and SQLite.
- Provide endpoints for health checks, technician creation, work-request creation, dispatch-plan generation, assignment status updates, audit log lookup, and summary reporting.
- Work requests include external_id, location, requested_skill, priority (1-5), estimated_minutes, due_at, and optional metadata.
- Technician records include name, skills, shift_start, shift_end, max_minutes_per_shift, and active flag.
- Normalize incoming work requests by trimming string fields, rejecting duplicate external_id values, validating priority and duration bounds, and storing metadata as JSON.
- Open work requests mean requests that are not DONE and not CANCELLED.
- Generate a dispatch plan for a given ISO date. Assign open work requests only to active technicians who have the required skill, enough remaining shift capacity, and a shift window that can finish the task before due_at. Higher priority jobs must be considered before lower priority jobs; ties use earlier due_at then external_id.
- Persist assignments with status values PLANNED, IN_PROGRESS, DONE, CANCELLED. Valid transitions are PLANNED to IN_PROGRESS or CANCELLED, IN_PROGRESS to DONE or CANCELLED, and no outgoing transitions from DONE or CANCELLED. Invalid state transitions must return clear errors and must not change stored data.
- Record an audit event for request creation, plan assignment, status changes, and cancellation. Audit entries must be queryable by work request id.
- Provide a summary endpoint for a date range with counts by status, unassigned request count, technician utilization minutes, and overdue open request count. A request is overdue in the summary if it is open and its due_at is before the end of the requested summary date range.
- Keep the code organized enough that validation, persistence, HTTP handling, and dispatch behavior can be understood and tested independently where that separation is useful.
- Use an API-key dependency for mutating endpoints. Mutations require an X-API-Key header matching DISPATCH_PLANNER_API_KEY, with a local/test default of "test-key"; read-only endpoints are public.
- Validate request payloads and return clear HTTP errors.
- Include pagination for work-request listing.
- Include tests for happy path planning, duplicate request rejection, skill mismatch, capacity limits, due_at tiebreaking within equal priority, due_at window exclusion, invalid status transitions, audit logging, unauthorized mutation, pagination, and summary metrics.
- Keep the design production-minded but not over-engineered.

Output contract:
- Actually create the project files in the current working directory.
- After creating files, print only a compact JSON object with keys "files_created", "entrypoint", and "test_command".
EOF
}

emit_task_prompt() {
  if [[ -n "$PROMPT_FILE" ]]; then
    cat "$PROMPT_FILE"
  else
    emit_default_prompt
  fi
}

build_prompt() {
  local arm="$1"

  case "$arm" in
    skills_off)
      ;;
    karpathy_only)
      ;;
    theory_only)
      ;;
    both)
      ;;
    *)
      error "unknown arm: $arm"
      ;;
  esac

  emit_task_prompt
}

build_claude_args_for_arm() {
  local arm="$1"
  CLAUDE_ARGS=(
    "--dangerously-skip-permissions"
    "--print"
    "--output-format"
    "text"
  )

  if ! is_false "$BARE"; then
    CLAUDE_ARGS+=("--bare")
  fi
  if ! is_false "$DISABLE_MCP"; then
    CLAUDE_ARGS+=("--strict-mcp-config" "--mcp-config" "$MCP_CONFIG_JSON")
  fi
  if [[ -n "$MODEL" ]]; then
    CLAUDE_ARGS+=("--model" "$MODEL")
  fi
  if [[ -n "$MAX_BUDGET_USD" ]]; then
    CLAUDE_ARGS+=("--max-budget-usd" "$MAX_BUDGET_USD")
  fi
}

run_one() {
  local arm="$1"
  local run_no="$2"
  local run_label
  run_label="$(printf '%02d' "$run_no")"

  local arm_dir="$RUN_DIR/$arm"
  local prompt_path="$arm_dir/prompt_${run_label}.txt"
  local out_path="$arm_dir/run_${run_label}.txt"
  local err_path="$arm_dir/run_${run_label}.stderr"
  local saved_work_dir="$arm_dir/workspaces/run_${run_label}"
  local run_work_dir=""
  local run_exec_dir
  local run_io_dir
  local run_prompt_path
  local run_out_path
  local run_err_path
  local claude_bin_path="$CLAUDE_BIN"
  mkdir -p "$arm_dir" "$arm_dir/workspaces" "$RUN_WORK_ROOT"
  run_work_dir="$(mktemp -d "$RUN_WORK_ROOT/skill-codegen.${RUN_ID}.${arm}.${run_label}.XXXXXX")"
  ACTIVE_RUN_WORK_DIR="$run_work_dir"
  run_exec_dir="$run_work_dir/workspace"
  run_io_dir="$run_work_dir/io"
  run_prompt_path="$run_io_dir/prompt.txt"
  run_out_path="$run_io_dir/stdout.txt"
  run_err_path="$run_io_dir/stderr.txt"
  mkdir -p "$run_exec_dir" "$run_io_dir"

  build_prompt "$arm" > "$run_prompt_path"

  build_claude_args_for_arm "$arm"

  printf '[%s %s] running Claude -> %s\n' "$arm" "$run_label" "$out_path" >&2

  local status=0
  if (
    cd "$run_exec_dir" || exit 1
    unset OLDPWD INIT_CWD
    unset BASH_ENV ENV CDPATH
    unset GIT_DIR GIT_WORK_TREE
    unset ORIGINAL_CWD SCRIPT_DIR PROMPT_FILE OUTPUT_ROOT RUN_WORK_ROOT
    unset MANAGED_SKILL_DIRS CLAUDE_GLOBAL_SKILL_DIR KARPATHY_SKILL THEORY_SKILL ARMS BARE
    unset DISABLE_MCP MCP_CONFIG_JSON
    unset MODEL MAX_BUDGET_USD KARPATHY_SKILL_FILE THEORY_SKILL_FILE
    unset RUN_ID RUN_DIR MANIFEST ACTIVE_RUN_WORK_DIR CLAUDE_BIN
    PWD="$run_exec_dir"
    GIT_CEILING_DIRECTORIES="$run_work_dir"
    export PWD GIT_CEILING_DIRECTORIES
    "$claude_bin_path" "${CLAUDE_ARGS[@]}" < "$run_prompt_path" > "$run_out_path" 2> "$run_err_path"
  ); then
    status=0
  else
    status=$?
  fi
  cp "$run_prompt_path" "$prompt_path"
  cp "$run_out_path" "$out_path"
  cp "$run_err_path" "$err_path"
  mv "$run_exec_dir" "$saved_work_dir"
  rm -rf "$run_work_dir"
  run_work_dir=""
  ACTIVE_RUN_WORK_DIR=""

  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$arm" "$run_label" "$status" "$saved_work_dir" "$prompt_path" "$out_path" "$err_path" >> "$MANIFEST"
  if [[ "$status" -ne 0 ]]; then
    printf '[%s %s] failed with status %s; stderr: %s\n' "$arm" "$run_label" "$status" "$err_path" >&2
    return 1
  fi
}

check_inputs

RUN_ID="$(date +%Y%m%d_%H%M%S)_$$"
RUN_DIR="$OUTPUT_ROOT/$RUN_ID"
MANIFEST="$RUN_DIR/manifest.tsv"
mkdir -p "$RUN_DIR"
printf 'arm\trun\tstatus\tworkspace\tprompt\tstdout\tstderr\n' > "$MANIFEST"

failures=0
for arm in $ARMS; do
  set_skill_state_for_arm "$arm"
  run_no=1
  while [[ "$run_no" -le "$REPEATS" ]]; do
    run_one "$arm" "$run_no" || failures=$((failures + 1))
    run_no=$((run_no + 1))
  done
done

printf 'manifest: %s\n' "$MANIFEST" >&2

if [[ "$failures" -ne 0 ]]; then
  error "$failures Claude run(s) failed"
fi
