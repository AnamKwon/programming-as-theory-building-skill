# Benchmark Notes

This folder contains the public, git-friendly summary of the local experiment runs plus copied raw result folders.

## Method

- Every generation ran in a fresh temporary workspace.
- Isolated arms are `skills_off`, `karpathy_only`, and `theory_only`.
- Code generation model setting: Claude Code `MODEL=haiku` (Claude Haiku).
- Review model: Claude Opus.
- Review rubric: `benchmark-codegen-review-v1`, a weighted score across task fulfillment, functional correctness, executability, test quality, code quality, minimality, and security/safety.

Two prompt families are present and should not be collapsed into one undifferentiated average:

- `basic-commerce`: the original 1,627-character prompt. It asks for a production-style FastAPI + SQLite inventory reservation and order orchestration service, but leaves several API details implicit.
- `strict-production`: the later 3,414-character prompt. It specifies exact endpoints, status codes, error bodies, 300-second expiration behavior, stock deduction/restoration semantics, 401 auth behavior, and pagination offset behavior.

## Run-Level Results

The table below is computed from parseable `review.txt` JSON files in `raw-results/.skill-review-runs/`. The `20260610_212232_30154` review run has two unusable review outputs: `karpathy_only/run_08` contains malformed JSON, and `skills_off/run_09` contains only an unfinished status message. Those two files are excluded from the averages below.

| Prompt family | Codegen run -> review run | Parsed reviews | `skills_off` | `karpathy_only` | `theory_only` | Winner | Notes |
| --- | --- | ---: | ---: | ---: | ---: | --- | --- |
| `basic-commerce` | `20260609_152615_16568` -> `20260609_170106_24348` | 30 | 66.8 | 72.2 | **78.8** | `theory_only` | Public copied review files contain the isolated arms used in this table. |
| `basic-commerce` | `20260609_195509_38196` -> `20260609_231224_49469` | 30 | 73.7 | 72.0 | **76.7** | `theory_only` | `skills_off` slightly beat `karpathy_only`; `theory_only` still led. |
| `basic-commerce` | `20260610_091239_64934` -> `20260610_102240_76453` | 30 | 72.9 | 74.4 | **77.5** | `theory_only` | Same prompt family as the 2026-06-09 runs. |
| `basic-commerce` | `20260610_092511_66275` -> `20260610_141815_93034` | 30 | 70.8 | 77.0 | **78.4** | `theory_only` | `karpathy_only` narrowed the gap but did not pass `theory_only`. |
| `strict-production` | `20260610_141237_92652` -> `20260610_153249_1692` | 30 | 83.3 | **84.3** | 82.0 | `karpathy_only` | Stricter prompt lifted all arms and made skill differences smaller. |
| `strict-production` | `20260610_202937_24877` -> `20260610_212232_30154` | 28 | 78.2 | 80.4 | **84.9** | `theory_only` | Two invalid/incomplete review outputs excluded. |

## Prompt-Family Aggregates

| Prompt family | Arm | n | Avg weighted | Functional | Executability | Test quality | Code quality | Minimality | Verdicts |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `basic-commerce` | `skills_off` | 40 | 71.0 | 61.4 | 68.9 | 65.8 | 78.7 | 73.7 | good:12, mixed:27, poor:1 |
| `basic-commerce` | `karpathy_only` | 40 | 73.9 | 63.8 | 71.0 | 70.5 | 80.5 | 76.9 | good:19, mixed:21 |
| `basic-commerce` | `theory_only` | 40 | **77.9** | **68.6** | **78.5** | **76.1** | **82.7** | **78.3** | good:27, mixed:13 |
| `strict-production` | `skills_off` | 19 | 80.9 | 76.6 | 74.2 | 80.3 | 88.6 | 79.4 | excellent:4, good:7, mixed:8 |
| `strict-production` | `karpathy_only` | 19 | 82.5 | 77.5 | **80.5** | 83.2 | 88.4 | 78.8 | excellent:5, good:5, mixed:9 |
| `strict-production` | `theory_only` | 20 | **83.4** | **81.8** | 77.8 | **83.8** | **90.1** | **80.8** | excellent:4, good:12, mixed:4 |
| all isolated | `skills_off` | 59 | 74.2 | 66.3 | 70.6 | 70.5 | 81.9 | 75.5 | excellent:4, good:19, mixed:35, poor:1 |
| all isolated | `karpathy_only` | 59 | 76.6 | 68.2 | 74.1 | 74.6 | 83.0 | 77.5 | excellent:5, good:24, mixed:30 |
| all isolated | `theory_only` | 60 | **79.7** | **73.0** | **78.3** | **78.6** | **85.2** | **79.2** | excellent:4, good:39, mixed:17 |

## Interpretation

The `basic-commerce` prompt is the cleaner test of skill behavior because the prompt leaves more program theory to be inferred. In that family, `theory_only` won all four runs. Its advantage was strongest in executability and tests: the skill tended to push the generated project toward service/repository/API boundaries, explicit edge-case handling, and more behavioral tests.

The `strict-production` prompt changed the experiment. Because the prompt itself spelled out status codes, expiration semantics, stock restoration, authentication behavior, and pagination, every arm improved. `skills_off` rose by +9.8 weighted points over its basic-prompt average, `karpathy_only` rose by +8.6, and `theory_only` rose by +5.6. That means the strict prompt absorbed part of the work that the theory-building skill had previously supplied.

`karpathy_only` showed its strongest result in `20260610_153249_1692`, where it narrowly beat the other arms. Its recurring profile is compact, readable code with better minimality than the baseline, but it still leaves domain failures when the prompt does not fully specify the invariant.

`theory_only` remains the best overall arm across all parseable isolated reviews. It is also the best arm in five of six run-level comparisons. Its cost is that generated code is often larger and still contains cleanup issues such as unused dependencies, stale README claims, dead helper functions, datetime deprecations, or runtime artifact leakage.

## Recurring Review Problems

Across both prompt families, the most common review findings were not syntax failures. They were theory failures:

- Inventory/reservation invariants: reservations did not always hold stock correctly, stock could be double-counted or restored incorrectly, or confirmed reservations could be reused.
- Idempotency: retries sometimes ignored payload mismatches or returned reconstructed data instead of the stored response.
- Expiration and state transitions: expired reservations, cancellation, confirmation, and order lifecycle rules were often only partially wired.
- Executability and DB isolation: SQLite thread handling, import errors, stray `commerce.db` files, and entrypoint/test-command mismatches appeared repeatedly.
- Test gaps: suites often tested status codes or happy paths without proving oversell prevention, expiration restoration, idempotency payload matching, or order state behavior.
- Minimality problems: unused response models, dead repository methods, unused dependencies, and README overclaims were common, including in stronger `theory_only` outputs.

## Raw Result Layout

The public `raw-results/` folder preserves the copied run layout:

- `raw-results/.skill-codegen-runs/<run_id>/manifest.tsv`
- `raw-results/.skill-codegen-runs/<run_id>/<arm>/prompt_*.txt`
- `raw-results/.skill-codegen-runs/<run_id>/<arm>/run_*.txt`
- `raw-results/.skill-codegen-runs/<run_id>/<arm>/workspaces/run_*/`
- `raw-results/.skill-review-runs/<run_id>/manifest.tsv`
- `raw-results/.skill-review-runs/<run_id>/<arm>/run_*/review.txt`

Generated SQLite databases, Python caches, and pytest caches are intentionally ignored.

`results-20260609.json` records the earlier 20-run aggregate and is kept as a historical snapshot. The current report above is derived directly from the copied raw review files.
