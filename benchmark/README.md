# Benchmark Notes

This folder contains the public, git-friendly summary of the local experiment runs plus copied raw result folders.

The benchmark code-generation tasks are published separately in
[prompts/](prompts/) so the prompt families can be inspected without digging
through copied raw run folders.

## Method

- Every generation ran in a fresh temporary workspace.
- Isolated arms are `skills_off`, `karpathy_only`, and `theory_only`.
- Code generation model setting: Claude Code `MODEL=haiku` (Claude Haiku).
- Review model: Claude Opus.
- Review rubric: `benchmark-codegen-review-v1`, a weighted score across task fulfillment, functional correctness, executability, test quality, code quality, minimality, and security/safety.

Three prompt families are present and should not be collapsed into one undifferentiated average:

- `basic-commerce`: the original 1,627-character prompt. It asks for a production-style FastAPI + SQLite inventory reservation and order orchestration service, but leaves several API details implicit.
- `strict-production`: the later 3,414-character prompt. It specifies exact endpoints, status codes, error bodies, 300-second expiration behavior, stock deduction/restoration semantics, 401 auth behavior, and pagination offset behavior.
- `strict-commerce-no-mcp`: the same 3,414-character strict commerce prompt, run after the harness was changed to disable MCP during generation/review. This is separated because the execution environment changed even though the prompt text stayed the same.

## Run-Level Results

The table below is computed from `review.txt` files that contain a directly extractable JSON object. Three review outputs are excluded from the averages: `20260610_212232_30154/karpathy_only/run_08` has malformed JSON, `20260610_212232_30154/skills_off/run_09` contains only an unfinished status message, and `20260611_013435_44809/karpathy_only/run_07` is prose/fence-wrapped in a way that the aggregation pass did not accept as directly parseable.

| Prompt family | Codegen run -> review run | Parsed reviews | `skills_off` | `karpathy_only` | `theory_only` | Winner | Notes |
| --- | --- | ---: | ---: | ---: | ---: | --- | --- |
| `basic-commerce` | `20260609_152615_16568` -> `20260609_170106_24348` | 30 | 66.8 | 72.2 | **78.8** | `theory_only` | Public copied review files contain the isolated arms used in this table. |
| `basic-commerce` | `20260609_195509_38196` -> `20260609_231224_49469` | 30 | 73.7 | 72.0 | **76.7** | `theory_only` | `skills_off` slightly beat `karpathy_only`; `theory_only` still led. |
| `basic-commerce` | `20260610_091239_64934` -> `20260610_102240_76453` | 30 | 72.9 | 74.4 | **77.5** | `theory_only` | Same prompt family as the 2026-06-09 runs. |
| `basic-commerce` | `20260610_092511_66275` -> `20260610_141815_93034` | 30 | 70.8 | 77.0 | **78.4** | `theory_only` | `karpathy_only` narrowed the gap but did not pass `theory_only`. |
| `strict-production` | `20260610_141237_92652` -> `20260610_153249_1692` | 30 | 83.3 | **84.3** | 82.0 | `karpathy_only` | Stricter prompt lifted all arms and made skill differences smaller. |
| `strict-production` | `20260610_202937_24877` -> `20260610_212232_30154` | 28 | 78.2 | 80.4 | **84.9** | `theory_only` | Two invalid/incomplete review outputs excluded. |
| `strict-commerce-no-mcp` | `20260611_002935_41179` -> `20260611_013435_44809` | 29 | 78.5 | 84.6 | **88.5** | `theory_only` | MCP-disabled run; one prose/fence-wrapped `karpathy_only` review excluded. |

## Run-Level Interpretation

- `20260609_152615_16568` -> `20260609_170106_24348`: `theory_only` led by 6.6 points over `karpathy_only` and 12.0 over `skills_off`. The baseline suffered most in functional correctness, executability, and test quality, which is the pattern expected when the prompt leaves domain invariants implicit.
- `20260609_195509_38196` -> `20260609_231224_49469`: `theory_only` still won, but the gap narrowed. `skills_off` beat `karpathy_only` on weighted score because this batch's `karpathy_only` outputs were more often penalized for functional correctness despite good minimality.
- `20260610_091239_64934` -> `20260610_102240_76453`: `theory_only` won mainly through executability and test quality. `karpathy_only` was better than baseline, but the edge was smaller than in the first run.
- `20260610_092511_66275` -> `20260610_141815_93034`: `karpathy_only` came close, but `theory_only` stayed ahead. Both skill arms beat `skills_off`, showing the clearest skill-on vs skill-off separation in the basic prompt family.
- `20260610_141237_92652` -> `20260610_153249_1692`: `karpathy_only` narrowly won. The strict prompt already supplied much of the domain theory, so compact implementation and lower accidental complexity mattered more.
- `20260610_202937_24877` -> `20260610_212232_30154`: `theory_only` recovered the lead with the same strict prompt. The larger difference came from functional correctness and test quality, while `karpathy_only` retained decent readability but had more mixed verdicts.
- `20260611_002935_41179` -> `20260611_013435_44809`: the MCP-disabled strict run produced the highest scores overall, especially for `theory_only`. `skills_off` had high test-quality scores but poor functional correctness, while `karpathy_only` improved strongly over both earlier prompt families.

## Prompt-Family Aggregates

| Prompt family | Arm | n | Avg weighted | Functional | Executability | Test quality | Code quality | Minimality | Verdicts |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| `basic-commerce` | `skills_off` | 40 | 71.0 | 61.4 | 68.9 | 65.8 | 78.7 | 73.7 | good:12, mixed:27, poor:1 |
| `basic-commerce` | `karpathy_only` | 40 | 73.9 | 63.8 | 71.0 | 70.5 | 80.5 | 76.9 | good:19, mixed:21 |
| `basic-commerce` | `theory_only` | 40 | **77.9** | **68.6** | **78.5** | **76.1** | **82.7** | **78.3** | good:27, mixed:13 |
| `strict-production` | `skills_off` | 19 | 80.9 | 76.6 | 74.2 | 80.3 | 88.6 | 79.4 | excellent:4, good:7, mixed:8 |
| `strict-production` | `karpathy_only` | 19 | 82.5 | 77.5 | **80.5** | 83.2 | 88.4 | 78.8 | excellent:5, good:5, mixed:9 |
| `strict-production` | `theory_only` | 20 | **83.4** | **81.8** | 77.8 | **83.8** | **90.1** | **80.8** | excellent:4, good:12, mixed:4 |
| `strict-commerce-no-mcp` | `skills_off` | 10 | 78.5 | 64.3 | 73.9 | 88.0 | 87.8 | 79.1 | excellent:2, good:2, mixed:6 |
| `strict-commerce-no-mcp` | `karpathy_only` | 9 | 84.6 | 82.8 | 83.7 | 82.9 | 89.2 | **81.0** | excellent:3, good:4, mixed:2 |
| `strict-commerce-no-mcp` | `theory_only` | 10 | **88.5** | **89.5** | **91.2** | **88.9** | **89.4** | 78.5 | excellent:4, good:6 |
| all isolated | `skills_off` | 69 | 74.8 | 66.0 | 71.1 | 73.0 | 82.7 | 76.1 | excellent:6, good:21, mixed:41, poor:1 |
| all isolated | `karpathy_only` | 68 | 77.7 | 70.1 | 75.4 | 75.7 | 83.8 | 78.0 | excellent:8, good:28, mixed:32 |
| all isolated | `theory_only` | 70 | **81.0** | **75.3** | **80.1** | **80.1** | **85.8** | **79.1** | excellent:8, good:45, mixed:17 |

## Code Shape Metrics

These are rough structure metrics from generated `src/`, `tests/`, and root Python entrypoint files only. They exclude caches, virtualenvs, generated DB files, and other runtime artifacts.

| Prompt family | Arm | n | Python LOC | Source LOC | Test LOC | Python files |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| `basic-commerce` | `skills_off` | 40 | 884 | 481 | 402 | 8.8 |
| `basic-commerce` | `karpathy_only` | 40 | 874 | 485 | 390 | 9.1 |
| `basic-commerce` | `theory_only` | 40 | 940 | 512 | 428 | 8.9 |
| `strict-production` | `skills_off` | 19 | 811 | 386 | 425 | 8.8 |
| `strict-production` | `karpathy_only` | 19 | 834 | 396 | 438 | 9.0 |
| `strict-production` | `theory_only` | 20 | 816 | 387 | 429 | 8.9 |
| `strict-commerce-no-mcp` | `skills_off` | 10 | 885 | 418 | 467 | 8.9 |
| `strict-commerce-no-mcp` | `karpathy_only` | 9 | 848 | 429 | 419 | 8.8 |
| `strict-commerce-no-mcp` | `theory_only` | 10 | 961 | 439 | 522 | 9.0 |

## Interpretation

The `basic-commerce` prompt is the cleaner test of skill behavior because the prompt leaves more program theory to be inferred. In that family, `theory_only` won all four complete runs. Its advantage was strongest in executability and tests: the skill tended to push the generated project toward clearer domain boundaries, explicit edge-case handling, and more behavioral tests.

The `strict-production` prompt changed the experiment. Because the prompt itself spelled out status codes, expiration semantics, stock restoration, authentication behavior, and pagination, every arm improved. `skills_off` rose by +9.8 weighted points over its basic-prompt average, `karpathy_only` rose by +8.6, and `theory_only` rose by +5.6. That means the strict prompt absorbed part of the work that the theory-building skill had previously supplied.

The MCP-disabled strict run is not directly interchangeable with the earlier strict-production runs because both tool availability and harness behavior changed. Within that run, however, the ranking was clear: `theory_only` scored 88.5, `karpathy_only` scored 84.6, and `skills_off` scored 78.5. The main separation was not code style; it was functional correctness and executability.

`karpathy_only` showed its strongest earlier result in `20260610_153249_1692`, where it narrowly beat the other arms. Its recurring profile is compact, readable code with good minimality and fewer speculative structures. The weakness is that compactness does not by itself recover missing business invariants; when the prompt leaves behavior implicit, it can still produce clean code that fails expiration, idempotency, auth, or state-transition details.

`theory_only` remains the best overall arm across all parseable isolated reviews. It is the best arm in six of seven run-level comparisons and has the best all-isolated average: 81.0 vs 77.7 for `karpathy_only` and 74.8 for `skills_off`. Its cost is size and cleanup pressure: it usually writes more test code and slightly more total Python LOC, and reviews still find unused dependencies, stale README claims, dead helpers, datetime deprecations, and runtime artifact leakage.

## Recurring Review Problems

Across the prompt families, the most common review findings were not syntax failures. They were theory failures:

- Inventory/reservation invariants: reservations did not always hold stock correctly, stock could be double-counted or restored incorrectly, or confirmed reservations could be reused.
- Idempotency: retries sometimes ignored payload mismatches or returned reconstructed data instead of the stored response.
- Expiration and state transitions: expired reservations, cancellation, confirmation, and order lifecycle rules were often only partially wired.
- Executability and DB isolation: SQLite thread handling, import errors, stray `commerce.db` files, and entrypoint/test-command mismatches appeared repeatedly.
- Test gaps: suites often tested status codes or happy paths without proving oversell prevention, expiration restoration, idempotency payload matching, or order state behavior.
- Minimality problems: unused response models, dead repository methods, unused dependencies, and README overclaims were common, including in stronger `theory_only` outputs.

By arm, the pattern is:

- `skills_off`: highest risk of locally plausible code with broken runtime behavior. The latest no-MCP run is representative: tests looked broad, but functional correctness averaged only 64.3 because several implementations still missed core stock/reservation behavior.
- `karpathy_only`: better compactness and readability than baseline, with strong performance when the prompt fully specifies the behavior. Its failures are usually missing or underspecified invariants rather than messy structure.
- `theory_only`: best at preserving domain behavior across implicit and strict prompts. Its recurring tradeoff is more code and more cleanup findings, not lower readability; the code-quality score is still highest overall.

## Raw Result Layout

The public `raw-results/` folder preserves the copied run layout:

- `raw-results/.skill-codegen-runs/<run_id>/manifest.tsv`
- `raw-results/.skill-codegen-runs/<run_id>/<arm>/prompt_*.txt`
- `raw-results/.skill-codegen-runs/<run_id>/<arm>/run_*.txt`
- `raw-results/.skill-codegen-runs/<run_id>/<arm>/workspaces/run_*/`
- `raw-results/.skill-review-runs/<run_id>/manifest.tsv`
- `raw-results/.skill-review-runs/<run_id>/<arm>/run_*/review.txt`

When joining codegen and review manifests, normalize the `run` column by numeric suffix: codegen manifests use values like `01`, while review manifests use values like `run_01`.

Generated SQLite databases, Python caches, and pytest caches are intentionally ignored.

`results-20260609.json` records the earlier 20-run aggregate and is kept as a historical snapshot. The current report above is derived directly from the copied raw review files and generated workspaces.
