# Benchmark Notes

This folder contains the public, git-friendly summary of the local experiment runs plus copied raw result folders.

## Method

- Same prompt for every generation.
- Fresh temporary workspace for every run.
- Three isolated arms: `skills_off`, `karpathy_only`, `theory_only`.
- 40 reviewed generations per arm in the comparable three-arm summary.
- Code generation model setting: Claude Code `MODEL=haiku` (Claude Haiku).
- Review model: Claude Opus.
- Review rubric: weighted score across task fulfillment, functional correctness, executability, test quality, code quality, minimality, and security/safety.

## Result file

The README table is currently based on four comparable review folders, excluding the non-comparable `20260610_153249_1692` folder because it contains only `karpathy_only` results. The headline aggregate is:

| Arm | Avg weighted total | Functional correctness | Test quality | Good verdicts | Mixed verdicts | Poor verdicts |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `skills_off` | 71.0 | 61.4 | 65.8 | 12/40 | 27/40 | 1/40 |
| `karpathy_only` | 73.9 | 63.8 | 70.5 | 19/40 | 21/40 | 0/40 |
| `theory_only` | 77.9 | 68.6 | 76.1 | 27/40 | 13/40 | 0/40 |

`results-20260609.json` records the earlier 20-run aggregate and is kept as a historical snapshot. The latest README table is derived from these copied raw-result folders:

- `raw-results/.skill-codegen-runs/20260609_152615_16568/`
- `raw-results/.skill-codegen-runs/20260609_195509_38196/`
- `raw-results/.skill-codegen-runs/20260610_091239_64934/`
- `raw-results/.skill-codegen-runs/20260610_092511_66275/`
- `raw-results/.skill-review-runs/20260609_170106_24348/`
- `raw-results/.skill-review-runs/20260609_231224_49469/`
- `raw-results/.skill-review-runs/20260610_102240_76453/`
- `raw-results/.skill-review-runs/20260610_141815_93034/`

The public `raw-results/` folder now preserves the original run layout:

- `raw-results/.skill-codegen-runs/<run_id>/manifest.tsv`
- `raw-results/.skill-codegen-runs/<run_id>/<arm>/prompt_*.txt`
- `raw-results/.skill-codegen-runs/<run_id>/<arm>/run_*.txt`
- `raw-results/.skill-codegen-runs/<run_id>/<arm>/workspaces/run_*/`
- `raw-results/.skill-review-runs/<run_id>/manifest.tsv`
- `raw-results/.skill-review-runs/<run_id>/<arm>/run_*/review.txt`

Generated SQLite databases, Python caches, and pytest caches are intentionally ignored.

The first included run also had a `both` arm. It is excluded from the headline three-arm summary because the comparable analysis isolates `skills_off`, `karpathy_only`, and `theory_only`.

`raw-results/.skill-review-runs/20260610_153249_1692/` is intentionally excluded from the headline comparison because it is not a complete three-arm run.
