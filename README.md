# Programming as Theory Building Skill

A Claude Code plugin and reusable coding-agent skill that turns code generation from prompt completion into theory-preserving engineering work.

Most coding-agent failures are not syntax failures. They are theory failures: the agent writes code that looks right, but does not understand the invariant the code protects, why the current boundary exists, where the change belongs, or what behavior proves the change is correct.

The skill is grounded in Peter Naur's paper "Programming as Theory Building" (1985). Naur's central claim is that the durable asset in programming is not only the program text, but the programmer's theory of how the program maps real-world affairs into behavior. This skill converts that idea into operational checks for coding agents: map the domain rule, explain the current shape, place the change beside the closest existing facility, and verify the behavior that matters.

## The Problem

General coding agents often produce plausible files that satisfy the prompt surface while missing the program's governing invariant. For code generation, that shows up as:

- new helpers or modules that do not match the existing domain boundary,
- tests that prove the happy path but not the business rule,
- speculative abstractions added before the current problem needs them,
- readable code whose design story is hard to extend safely.

`programming-as-theory-building` narrows the agent's behavior around the question Naur's paper makes unavoidable: what theory of the program is being preserved or extended?

## The Solution

The plugin packages one Claude Code skill and one project-level `CLAUDE.md` guideline file. The skill asks the agent to answer these checks before non-trivial code work:

| Principle | Addresses |
| --- | --- |
| **Rebuild the theory** | Context-free patches and wrong assumptions |
| **Place by similarity** | Misplaced helpers, duplicated domain concepts |
| **Keep changes surgical** | Drive-by rewrites and unrelated cleanup |
| **Avoid speculative flexibility** | Bloated abstractions and unused options |
| **Verify the theory** | Tests that pass without proving the domain rule |

That makes the agent inspect code paths, names, tests, docs, and runtime behavior before editing. It also discourages one-off abstractions and asks for verification tied to the domain behavior, not just syntax.

## Benchmark summary

The comparison used the same commerce-backend code generation prompt across three arms:

- `skills_off`: managed Claude Code skills disabled.
- `karpathy_only`: only the Karpathy guidelines skill enabled.
- `theory_only`: only this Programming as Theory Building skill enabled.

Code generation used **Claude Haiku** through the Claude Code `MODEL=haiku` setting for every arm. Each arm ran 20 independent generations in a fresh temporary workspace. The generated projects were then reviewed by a separate Claude Opus review pass using a weighted rubric for task fulfillment, functional correctness, executability, test quality, code quality, minimality, and security/safety.

Latest comparable 3-arm summary used:

- Codegen runs: `benchmark/raw-results/.skill-codegen-runs/20260609_152615_16568`, `benchmark/raw-results/.skill-codegen-runs/20260609_195509_38196`
- Review runs: `benchmark/raw-results/.skill-review-runs/20260609_170106_24348`, `benchmark/raw-results/.skill-review-runs/20260609_231224_49469`
- Codegen model setting: `MODEL=haiku`
- Repeats: 20 per arm, 60 total reviewed projects
- Prompt: FastAPI + SQLite inventory reservation and order orchestration API
- Reviewer rubric: `benchmark-codegen-review-v1`

| Arm | Avg weighted total | Functional correctness | Test quality | Good verdicts | Mixed verdicts | Poor verdicts |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `skills_off` | 70.2 | 59.7 | 65.0 | 5/20 | 14/20 | 1/20 |
| `karpathy_only` | 72.1 | 59.8 | 68.0 | 7/20 | 13/20 | 0/20 |
| `theory_only` | 77.8 | 69.2 | 75.5 | 12/20 | 8/20 | 0/20 |

The largest difference was not formatting or surface completeness. `theory_only` improved the reviewer-scored correctness of the generated business rules: stock availability, idempotency, reservation expiration, order state transitions, and error behavior. Across 20 runs per arm, it led `skills_off` by +7.6 weighted-total points and +9.5 functional-correctness points. It led `karpathy_only` by +5.7 weighted-total points and +9.4 functional-correctness points.

## Interpreting the result

The baseline without skills was already capable of producing complete-looking FastAPI projects, but the review repeatedly found hidden domain failures: tests passing while stock was not actually reserved, order state transitions diverging from reservation state, or generated code leaving committed database artifacts and unused schemas.

The Karpathy-only arm was useful as general coding discipline and slightly outperformed `skills_off` on weighted total and good-verdict count in this 20-run summary. Its functional-correctness score was nearly tied with the baseline, though. The pattern in review findings suggests that broad "good code" guidance can still miss the exact invariant unless the agent is forced to rebuild the program's domain theory.

The theory-only arm was not perfect. Review still found oversell, expiration, and validation bugs in some runs. The useful signal is that it shifted the distribution: more `good` verdicts, higher average functional correctness, and clearer service/repository/API boundaries tied to the requested workflow.

The public benchmark files include the aggregate summary plus raw copied codegen/review run folders:

- `benchmark/results-20260609.json`
- `benchmark/raw-results/.skill-codegen-runs/`
- `benchmark/raw-results/.skill-review-runs/`

The 20-run aggregate uses the two complete 2026-06-09 review sets. Additional 2026-06-10 raw folders are included for auditability, but they are partial review runs and are not included in the headline three-arm summary.
Generated SQLite databases, Python caches, and pytest caches are intentionally ignored.

## Install

Option A: Claude Code plugin

```text
/plugin marketplace add <github-owner>/programming-as-theory-building-skill
/plugin install programming-as-theory-building-skill@programming-as-theory-building
```

Replace `<github-owner>` with the account or organization that publishes this repository.

Option B: manual Claude Code skill install

```bash
mkdir -p ~/.claude/skills/programming-as-theory-building
cp skills/programming-as-theory-building/SKILL.md ~/.claude/skills/programming-as-theory-building/SKILL.md
```

Option C: per-project `CLAUDE.md`

```bash
cp CLAUDE.md /path/to/project/CLAUDE.md
```

For Codex CLI, copy the operating rules into `AGENTS.md`; Codex does not import Claude Code `SKILL.md` automatically. For Gemini CLI, put the rules in `GEMINI.md`, or import the skill content with the CLI's memory mechanism.

## How to Know It's Working

These guidelines are working if you see:

- fewer isolated helpers that ignore existing service/repository/UI boundaries,
- fewer broad rewrites when a local change would preserve the theory,
- more explicit invariant checks before implementation,
- final summaries that connect `Theory`, `Changed`, `Verified`, and `Risk`.

## Reproduce the benchmark

From the parent experiment workspace, run two 10-repeat sets and aggregate the comparable three-arm results:

```bash
MODEL=haiku REPEATS=10 ARMS="skills_off karpathy_only theory_only" ./run_skill_codegen_experiment.sh
MODEL=opus ./run_opus_code_review_experiment.sh .skill-codegen-runs/<run_id>
```

The published summary combines two complete 10-repeat review sets. A fresh `REPEATS=20` run can produce the same sample size, but it will not reproduce the exact copied run ids.

The benchmark harness intentionally keeps `both` out of the default comparison set. `ARMS=both` remains available as an explicit opt-in, but the default comparison isolates single-skill effects.

## Citation

Naur, Peter. "Programming as Theory Building." *Microprocessing and Microprogramming*, vol. 15, no. 5, 1985, pp. 253-261.

## Repository layout

```text
.
|-- README.md
|-- PROMOTION.md
|-- LICENSE
|-- CITATION.cff
|-- CLAUDE.md
|-- .claude-plugin/
|   `-- plugin.json
|-- benchmark/
|   |-- README.md
|   |-- raw-results/
|   |   |-- .skill-codegen-runs/
|   |   `-- .skill-review-runs/
|   `-- results-20260609.json
|-- skills/
|   `-- programming-as-theory-building/
|       `-- SKILL.md
`-- .gitignore
```
