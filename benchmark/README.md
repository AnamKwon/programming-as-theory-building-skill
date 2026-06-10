# Benchmark Notes

This folder contains the public, git-friendly summary of the local experiment runs. Raw run folders are intentionally ignored because they contain many generated projects and transient review artifacts.

## Method

- Same prompt for every generation.
- Fresh temporary workspace for every run.
- Three isolated arms: `skills_off`, `karpathy_only`, `theory_only`.
- 10 generations per arm.
- Code generation model setting: Claude Code `MODEL=haiku` (Claude Haiku).
- Review model: Claude Opus.
- Review rubric: weighted score across task fulfillment, functional correctness, executability, test quality, code quality, minimality, and security/safety.

## Result file

`results-20260609.json` records the aggregated scores used in the README table. It is derived from:

- `.skill-codegen-runs/20260609_195509_38196/manifest.tsv`
- `.skill-review-runs/20260609_231224_49469/manifest.tsv`
- `.skill-review-runs/20260609_231224_49469/*/*/review.txt`

The raw local review files include full per-run findings. The public summary keeps only aggregate metrics and high-level interpretation.
