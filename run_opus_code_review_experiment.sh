#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  ./run_opus_code_review_experiment.sh [codegen-run-dir]

Runs Claude Code in print mode from each generated workspace and saves an
independent code-review/readability/unnecessary-code evaluation for later
aggregation.

Arguments:
  codegen-run-dir defaults to the latest .skill-codegen-runs/<run_id> directory.

Environment:
  CLAUDE_BIN=claude
  MODEL=opus
  OUTPUT_ROOT=.skill-review-runs
  RUN_WORK_ROOT=$TMPDIR
  WORKSPACE_GLOB="*/workspaces/run_*"
  BARE=0
  DISABLE_MCP=1
  MCP_CONFIG_JSON='{"mcpServers":{}}'
  MAX_BUDGET_USD=

Output:
  Results are written under OUTPUT_ROOT/<timestamp>/.
  Each review starts with the generated workspace as Claude's current directory.
  The saved stdout file contains Claude's printed review result.
EOF
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

ORIGINAL_CWD="$(pwd)"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
cd "$SCRIPT_DIR"

CLAUDE_BIN="${CLAUDE_BIN:-claude}"
MODEL="${MODEL:-opus}"
OUTPUT_ROOT="${OUTPUT_ROOT:-.skill-review-runs}"
RUN_WORK_ROOT="${RUN_WORK_ROOT:-${TMPDIR:-/tmp}}"
WORKSPACE_GLOB="${WORKSPACE_GLOB:-*/workspaces/run_*}"
BARE="${BARE:-0}"
DISABLE_MCP="${DISABLE_MCP:-1}"
if [[ -z "${MCP_CONFIG_JSON+x}" ]]; then
  MCP_CONFIG_JSON='{"mcpServers":{}}'
fi
MAX_BUDGET_USD="${MAX_BUDGET_USD:-}"
CODEGEN_RUN_DIR="${1:-${CODEGEN_RUN_DIR:-}}"

if [[ "$OUTPUT_ROOT" != /* ]]; then
  OUTPUT_ROOT="$SCRIPT_DIR/$OUTPUT_ROOT"
fi
if [[ "$RUN_WORK_ROOT" != /* ]]; then
  RUN_WORK_ROOT="${TMPDIR:-/tmp}/$RUN_WORK_ROOT"
fi

ACTIVE_REVIEW_WORK_DIR=""

error() {
  printf 'error: %s\n' "$*" >&2
  exit 1
}

cleanup_active_review_work_dir() {
  if [[ -n "${ACTIVE_REVIEW_WORK_DIR:-}" && -d "$ACTIVE_REVIEW_WORK_DIR" ]]; then
    rm -rf "$ACTIVE_REVIEW_WORK_DIR" || true
  fi
}

trap cleanup_active_review_work_dir EXIT
trap 'cleanup_active_review_work_dir; exit 130' INT
trap 'cleanup_active_review_work_dir; exit 143' TERM

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

copy_workspace() {
  local source_dir="$1"
  local target_dir="$2"
  local file_path
  local copied=0

  while IFS= read -r -d '' file_path; do
    mkdir -p "$target_dir/$(dirname "$file_path")" || return 1
    cp "$source_dir/${file_path#./}" "$target_dir/$file_path" || return 1
    copied=$((copied + 1))
  done < <(
    cd "$source_dir" || exit 1
    find . \
      -path '*/.git' -prune -o \
      -path './.venv' -prune -o \
      -path './venv' -prune -o \
      -path './__pycache__' -prune -o \
      -path './.pytest_cache' -prune -o \
      -path './.mypy_cache' -prune -o \
      -path './.ruff_cache' -prune -o \
      -path './.benchmarks' -prune -o \
      -type f -print0
  )

  [[ "$copied" -gt 0 ]] || return 1
}

latest_codegen_run_dir() {
  local latest
  latest="$(find "$SCRIPT_DIR/.skill-codegen-runs" -mindepth 1 -maxdepth 1 -type d -print 2>/dev/null | sort | tail -n 1)"
  [[ -n "$latest" ]] || return 1
  printf '%s\n' "$latest"
}

resolve_codegen_run_dir() {
  if [[ -z "$CODEGEN_RUN_DIR" ]]; then
    latest_codegen_run_dir || error "no .skill-codegen-runs/<run_id> directory found"
    return
  fi

  if [[ "$CODEGEN_RUN_DIR" != /* ]]; then
    CODEGEN_RUN_DIR="$ORIGINAL_CWD/$CODEGEN_RUN_DIR"
  fi
  [[ -d "$CODEGEN_RUN_DIR" ]] || error "codegen run directory not found: $CODEGEN_RUN_DIR"
  canonicalize_path "$CODEGEN_RUN_DIR"
}

emit_review_prompt() {
  cat <<'EOF'
You are reviewing generated code from a coding-agent experiment.

Focus on code review, not rewriting. Inspect the current working directory only.
Do not read parent directories or sibling experiment outputs.

Evaluate the generated implementation using the benchmark-style rubric below.

If practical, inspect the files and run lightweight local checks such as:
- listing the project files,
- reading pyproject.toml and README.md,
- reviewing src/ and tests/,
- running the declared test command if dependencies are already available or cheap to install.

Do not modify files.

Use a benchmark-style LLM code-generation evaluation. Score every breakdown item
on a 0-100 integer scale. Each top-level category score is the rounded average
of its breakdown item scores. Use the category weights exactly as written, and
calculate "weighted_total" from the weighted implementation-quality scores only.
Do not include review_confidence_score in weighted_total. Prefer concrete file
references in notes, especially when subtracting points. Award high scores only
when there is evidence from code inspection or commands.

Weighted total formula:
weighted_total =
  task_fulfillment_score * 0.20 +
  functional_correctness_score * 0.25 +
  executability_score * 0.15 +
  test_quality_score * 0.15 +
  code_quality_score * 0.10 +
  minimality_score * 0.10 +
  security_safety_score * 0.05

Round weighted_total to one decimal place. The category weights sum to 1.00.
Also return weighted_components, where each value is category_score * weight,
rounded to one decimal place.

Verdict thresholds:
- excellent: weighted_total 90.0-100.0 and no serious correctness gaps.
- good: weighted_total 75.0-89.9 and the project is mostly usable.
- mixed: weighted_total 55.0-74.9 or usable only with clear fixes.
- poor: weighted_total 30.0-54.9 with major missing behavior or maintainability problems.
- failed: weighted_total 0.0-29.9, cannot be evaluated, or does not form a coherent project.

Detailed rubric:
- task_fulfillment_score, 0-100, weight 0.20:
  - instruction_compliance: follows the prompt and output contract.
  - required_artifacts: creates the requested files and project structure.
  - feature_coverage: implements the requested API surface and workflows.
  - constraint_adherence: respects "fresh workspace", no parent reads, and production-minded constraints.
- functional_correctness_score, 0-100, weight 0.25:
  - domain_invariants: stock availability, idempotency, expiration, and order state transitions hold.
  - edge_case_behavior: insufficient stock, duplicate/idempotent retry, expired reservation, unauthorized mutation, pagination.
  - data_consistency: persistence updates are coherent and transaction risks are understood.
  - error_semantics: clear and appropriate HTTP status codes and error bodies.
- executability_score, 0-100, weight 0.15:
  - installability: dependencies and packaging are complete and plausible.
  - runtime_entrypoints: app entrypoint, imports, and configuration defaults are usable.
  - command_result: tests or smoke checks run successfully, or failures are well isolated.
  - runtime_isolation: no dependence on parent directories, hidden local files, generated siblings, or ambient state.
- test_quality_score, 0-100, weight 0.15:
  - required_test_coverage: covers happy paths, insufficient stock, idempotency, expiration, auth, and pagination.
  - behavioral_assertions: tests prove domain behavior rather than only status codes.
  - integration_realism: tests exercise API/service behavior with realistic persistence.
  - repeatability: tests isolate database/state and can run repeatedly.
- code_quality_score, 0-100, weight 0.10:
  - readability: names, module boundaries, and control flow are easy to follow.
  - maintainability: future rule changes are localized and invariants are visible.
  - boundary_design: database access, service logic, schemas, and security are coherently separated.
  - documentation_quality: README/docstrings clarify operation without padding or false claims.
- minimality_score, 0-100, weight 0.10:
  - no_speculative_infrastructure: avoids unused queues, workers, migrations, CLIs, providers, or frameworks.
  - no_dead_or_duplicate_code: avoids unused imports, unused models, duplicate helpers, and unreachable branches.
  - appropriate_abstractions: abstractions are justified by current behavior, not future guesses.
  - dependency_minimality: dependencies are justified by used functionality.
- security_safety_score, 0-100, weight 0.05:
  - auth_enforcement: mutating endpoints require the API-key dependency.
  - secret_handling: no hardcoded real secrets or unsafe leakage.
  - input_safety: validates untrusted inputs and avoids obvious injection/data-integrity risks.
  - unsafe_operations: avoids unnecessary shell, file, network, or destructive operations.
- review_confidence_score, 0-100, meta score not included in weighted_total:
  - inspection_depth: enough files were reviewed to support the score.
  - command_evidence: commands run are relevant and results are captured.
  - issue_specificity: findings cite concrete files/functions.
  - uncertainty_handling: limitations are stated without hiding risk.

Set review_risk to a short sentence describing any limits of the review, such as
commands not run, dependencies unavailable, truncated inspection, or uncertainty
about runtime behavior. Use "low" only when files and relevant commands were
checked sufficiently.

Return JSON only with this schema:
{
  "rubric_version": "benchmark-codegen-review-v1",
  "score_scale": "0-100 per category",
  "weights": {
    "task_fulfillment": 0.20,
    "functional_correctness": 0.25,
    "executability": 0.15,
    "test_quality": 0.15,
    "code_quality": 0.10,
    "minimality": 0.10,
    "security_safety": 0.05
  },
  "task_fulfillment_score": 0-100,
  "task_fulfillment_breakdown": {
    "instruction_compliance": 0-100,
    "required_artifacts": 0-100,
    "feature_coverage": 0-100,
    "constraint_adherence": 0-100
  },
  "functional_correctness_score": 0-100,
  "functional_correctness_breakdown": {
    "domain_invariants": 0-100,
    "edge_case_behavior": 0-100,
    "data_consistency": 0-100,
    "error_semantics": 0-100
  },
  "executability_score": 0-100,
  "executability_breakdown": {
    "installability": 0-100,
    "runtime_entrypoints": 0-100,
    "command_result": 0-100,
    "runtime_isolation": 0-100
  },
  "test_quality_score": 0-100,
  "test_quality_breakdown": {
    "required_test_coverage": 0-100,
    "behavioral_assertions": 0-100,
    "integration_realism": 0-100,
    "repeatability": 0-100
  },
  "code_quality_score": 0-100,
  "code_quality_breakdown": {
    "readability": 0-100,
    "maintainability": 0-100,
    "boundary_design": 0-100,
    "documentation_quality": 0-100
  },
  "minimality_score": 0-100,
  "minimality_breakdown": {
    "no_speculative_infrastructure": 0-100,
    "no_dead_or_duplicate_code": 0-100,
    "appropriate_abstractions": 0-100,
    "dependency_minimality": 0-100
  },
  "security_safety_score": 0-100,
  "security_safety_breakdown": {
    "auth_enforcement": 0-100,
    "secret_handling": 0-100,
    "input_safety": 0-100,
    "unsafe_operations": 0-100
  },
  "review_confidence_score": 0-100,
  "review_confidence_breakdown": {
    "inspection_depth": 0-100,
    "command_evidence": 0-100,
    "issue_specificity": 0-100,
    "uncertainty_handling": 0-100
  },
  "weighted_components": {
    "task_fulfillment": 0.0-20.0,
    "functional_correctness": 0.0-25.0,
    "executability": 0.0-15.0,
    "test_quality": 0.0-15.0,
    "code_quality": 0.0-10.0,
    "minimality": 0.0-10.0,
    "security_safety": 0.0-5.0
  },
  "weighted_total": 0.0-100.0,
  "verdict": "excellent|good|mixed|poor|failed",
  "key_findings": ["..."],
  "score_rationale": {
    "task_fulfillment": "...",
    "functional_correctness": "...",
    "executability": "...",
    "test_quality": "...",
    "code_quality": "...",
    "minimality": "...",
    "security_safety": "...",
    "review_confidence": "..."
  },
  "instruction_failures": ["..."],
  "correctness_failures": ["..."],
  "execution_failures": ["..."],
  "test_gaps": ["..."],
  "quality_notes": ["..."],
  "unnecessary_code_examples": ["..."],
  "security_safety_notes": ["..."],
  "file_evidence": [
    {"path": "...", "note": "..."}
  ],
  "commands_run": ["..."],
  "review_risk": "..."
}
EOF
}

build_claude_args() {
  CLAUDE_ARGS=(
    "--dangerously-skip-permissions"
    "--print"
    "--output-format"
    "text"
    "--model"
    "$MODEL"
  )

  if ! is_false "$BARE"; then
    CLAUDE_ARGS+=("--bare")
  fi
  if ! is_false "$DISABLE_MCP"; then
    CLAUDE_ARGS+=("--strict-mcp-config" "--mcp-config" "$MCP_CONFIG_JSON")
  fi
  if [[ -n "$MAX_BUDGET_USD" ]]; then
    CLAUDE_ARGS+=("--max-budget-usd" "$MAX_BUDGET_USD")
  fi
}

workspace_label() {
  local workspace="$1"
  local arm
  local run

  arm="$(basename "$(dirname "$(dirname "$workspace")")")"
  run="$(basename "$workspace")"
  printf '%s\t%s' "$arm" "$run"
}

run_review_one() {
  local workspace="$1"
  local arm
  local run
  local review_dir
  local saved_prompt_path
  local saved_out_path
  local saved_err_path
  local review_work_dir=""
  local review_exec_dir
  local review_io_dir
  local prompt_path
  local out_path
  local err_path
  local status=0

  IFS=$'\t' read -r arm run < <(workspace_label "$workspace")
  review_dir="$RUN_DIR/$arm/$run"
  saved_prompt_path="$review_dir/prompt.txt"
  saved_out_path="$review_dir/review.txt"
  saved_err_path="$review_dir/review.stderr"
  mkdir -p "$review_dir"

  mkdir -p "$RUN_WORK_ROOT"
  review_work_dir="$(mktemp -d "$RUN_WORK_ROOT/skill-review.${RUN_ID}.${arm}.${run}.XXXXXX")"
  ACTIVE_REVIEW_WORK_DIR="$review_work_dir"
  review_exec_dir="$review_work_dir/workspace"
  review_io_dir="$review_work_dir/io"
  prompt_path="$review_io_dir/prompt.txt"
  out_path="$review_io_dir/review.txt"
  err_path="$review_io_dir/review.stderr"
  mkdir -p "$review_exec_dir" "$review_io_dir"
  copy_workspace "$workspace" "$review_exec_dir"

  emit_review_prompt > "$prompt_path"
  build_claude_args

  printf '[%s %s] reviewing workspace -> %s\n' "$arm" "$run" "$saved_out_path" >&2

  if (
    cd "$review_exec_dir" || exit 1
    unset OLDPWD INIT_CWD
    unset BASH_ENV ENV CDPATH
    unset GIT_DIR GIT_WORK_TREE
    unset ORIGINAL_CWD SCRIPT_DIR CODEGEN_RUN_DIR OUTPUT_ROOT RUN_WORK_ROOT WORKSPACE_GLOB
    unset MODEL MAX_BUDGET_USD BARE DISABLE_MCP MCP_CONFIG_JSON CLAUDE_BIN RUN_ID RUN_DIR MANIFEST ACTIVE_REVIEW_WORK_DIR
    PWD="$review_exec_dir"
    GIT_CEILING_DIRECTORIES="$review_work_dir"
    export PWD GIT_CEILING_DIRECTORIES
    "$CLAUDE_BIN_RESOLVED" "${CLAUDE_ARGS[@]}" < "$prompt_path" > "$out_path" 2> "$err_path"
  ); then
    status=0
  else
    status=$?
  fi

  cp "$prompt_path" "$saved_prompt_path"
  cp "$out_path" "$saved_out_path"
  cp "$err_path" "$saved_err_path"
  rm -rf "$review_work_dir"
  review_work_dir=""
  ACTIVE_REVIEW_WORK_DIR=""

  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$arm" "$run" "$status" "$workspace" "$saved_prompt_path" "$saved_out_path" "$saved_err_path" >> "$MANIFEST"
  if [[ "$status" -ne 0 ]]; then
    printf '[%s %s] review failed with status %s; stderr: %s\n' "$arm" "$run" "$status" "$saved_err_path" >&2
    return 1
  fi
}

CLAUDE_BIN_RESOLVED="$(command -v "$CLAUDE_BIN")" || error "Claude binary not found: $CLAUDE_BIN"
CODEGEN_RUN_DIR="$(resolve_codegen_run_dir)"
OUTPUT_ROOT="$(canonicalize_path "$OUTPUT_ROOT")" || error "cannot resolve OUTPUT_ROOT: $OUTPUT_ROOT"
RUN_WORK_ROOT="$(canonicalize_path "$RUN_WORK_ROOT")" || error "cannot resolve RUN_WORK_ROOT: $RUN_WORK_ROOT"
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

RUN_ID="$(date +%Y%m%d_%H%M%S)_$$"
RUN_DIR="$OUTPUT_ROOT/$RUN_ID"
MANIFEST="$RUN_DIR/manifest.tsv"
mkdir -p "$RUN_DIR"
printf 'arm\trun\tstatus\tworkspace\tprompt\tstdout\tstderr\n' > "$MANIFEST"

mapfile -t WORKSPACES < <(
  cd "$CODEGEN_RUN_DIR"
  find . -path "./$WORKSPACE_GLOB" -type d ! -path "./$WORKSPACE_GLOB/*" -print | sort
)

if [[ "${#WORKSPACES[@]}" -eq 0 ]]; then
  error "no workspaces found under $CODEGEN_RUN_DIR using glob $WORKSPACE_GLOB"
fi

failures=0
for workspace in "${WORKSPACES[@]}"; do
  workspace="$CODEGEN_RUN_DIR/${workspace#./}"
  run_review_one "$workspace" || failures=$((failures + 1))
done

printf 'manifest: %s\n' "$MANIFEST" >&2

if [[ "$failures" -ne 0 ]]; then
  error "$failures Claude review run(s) failed"
fi
