# Benchmark Notes

This folder contains the public, git-friendly summary of the local experiment runs plus copied raw result folders.

## Method

- Same prompt for every generation.
- Fresh temporary workspace for every run.
- Three isolated arms: `skills_off`, `karpathy_only`, `theory_only`.
- 20 reviewed generations per arm in the comparable three-arm summary.
- Code generation model setting: Claude Code `MODEL=haiku` (Claude Haiku).
- Review model: Claude Opus.
- Review rubric: weighted score across task fulfillment, functional correctness, executability, test quality, code quality, minimality, and security/safety.

## Result file

`results-20260609.json` records the aggregated scores used in the README table. It is derived from these copied raw-result folders:

- `raw-results/.skill-codegen-runs/20260609_152615_16568/`
- `raw-results/.skill-codegen-runs/20260609_195509_38196/`
- `raw-results/.skill-review-runs/20260609_170106_24348/`
- `raw-results/.skill-review-runs/20260609_231224_49469/`

The public `raw-results/` folder now preserves the original run layout:

- `raw-results/.skill-codegen-runs/<run_id>/manifest.tsv`
- `raw-results/.skill-codegen-runs/<run_id>/<arm>/prompt_*.txt`
- `raw-results/.skill-codegen-runs/<run_id>/<arm>/run_*.txt`
- `raw-results/.skill-codegen-runs/<run_id>/<arm>/workspaces/run_*/`
- `raw-results/.skill-review-runs/<run_id>/manifest.tsv`
- `raw-results/.skill-review-runs/<run_id>/<arm>/run_*/review.txt`

Generated SQLite databases, Python caches, and pytest caches are intentionally ignored.

The first included run also had a `both` arm. It is excluded from the 20-run three-arm summary because the later comparable run only contains `skills_off`, `karpathy_only`, and `theory_only`.

Additional raw folders from 2026-06-10 are included for auditability:

- `raw-results/.skill-codegen-runs/20260610_091239_64934/`
- `raw-results/.skill-codegen-runs/20260610_092511_66275/`
- `raw-results/.skill-review-runs/20260610_102240_76453/`

The 2026-06-10 review run is partial (`karpathy_only` 10, `skills_off` 4, `theory_only` 0 in its manifest), so it is not included in `results-20260609.json`.
