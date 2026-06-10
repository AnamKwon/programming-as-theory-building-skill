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

Code generation used **Claude Haiku** through the Claude Code `MODEL=haiku` setting for every arm. Each arm ran independent generations in a fresh temporary workspace. The generated projects were then reviewed by a separate Claude Opus review pass using a weighted rubric for task fulfillment, functional correctness, executability, test quality, code quality, minimality, and security/safety.

Latest comparable 3-arm summary used:

- Codegen runs: `benchmark/raw-results/.skill-codegen-runs/20260609_152615_16568`, `benchmark/raw-results/.skill-codegen-runs/20260609_195509_38196`, `benchmark/raw-results/.skill-codegen-runs/20260610_091239_64934`, `benchmark/raw-results/.skill-codegen-runs/20260610_092511_66275`
- Review runs: `benchmark/raw-results/.skill-review-runs/20260609_170106_24348`, `benchmark/raw-results/.skill-review-runs/20260609_231224_49469`, `benchmark/raw-results/.skill-review-runs/20260610_102240_76453`, `benchmark/raw-results/.skill-review-runs/20260610_141815_93034`
- Codegen model setting: `MODEL=haiku`
- Repeats: 40 per arm, 120 total reviewed projects
- Prompt: FastAPI + SQLite inventory reservation and order orchestration API
- Reviewer rubric: `benchmark-codegen-review-v1`
- Excluded run: `benchmark/raw-results/.skill-review-runs/20260610_153249_1692` because it is not a comparable three-arm run.

| Arm | Avg weighted total | Functional correctness | Test quality | Good verdicts | Mixed verdicts | Poor verdicts |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `skills_off` | 71.0 | 61.4 | 65.8 | 12/40 | 27/40 | 1/40 |
| `karpathy_only` | 73.9 | 63.8 | 70.5 | 19/40 | 21/40 | 0/40 |
| `theory_only` | 77.9 | 68.6 | 76.1 | 27/40 | 13/40 | 0/40 |

The largest difference was not formatting or surface completeness. `theory_only` improved the reviewer-scored correctness of the generated business rules: stock availability, idempotency, reservation expiration, order state transitions, and error behavior. Across 40 runs per arm, it led `skills_off` by +6.8 weighted-total points, +7.2 functional-correctness points, +9.6 executability points, and +10.3 test-quality points. It led `karpathy_only` by +4.0 weighted-total points and +4.8 functional-correctness points.

## Interpreting the result

The baseline without skills was already capable of producing complete-looking FastAPI projects, but the review repeatedly found hidden domain failures: tests passing while stock was not actually reserved, order state transitions diverging from reservation state, or generated code leaving committed database artifacts and unused schemas.

The Karpathy-only arm was useful as general coding discipline and outperformed `skills_off` on weighted total, test quality, minimality, and good-verdict count in this 40-run summary. It still repeatedly missed important commerce invariants: reservations that did not actually hold inventory, non-atomic confirmation flows, idempotency retries that ignored payload changes, and incomplete order lifecycle wiring. The pattern in review findings suggests that broad "good code" guidance can improve shape and readability while still missing the exact invariant unless the agent is forced to rebuild the program's domain theory.

The theory-only arm was not perfect. Review still found reservation reuse, expiration cleanup, idempotency, unused dependency, README mismatch, and deprecated API issues in some runs. The useful signal is that it shifted the distribution: more `good` verdicts, higher average functional correctness, better executability, stronger tests, and clearer service/repository/API boundaries tied to the requested workflow.

The public benchmark files include the aggregate summary plus raw copied codegen/review run folders:

- `benchmark/results-20260609.json`
- `benchmark/raw-results/.skill-codegen-runs/`
- `benchmark/raw-results/.skill-review-runs/`

The headline aggregate now uses four comparable three-arm review sets and excludes `20260610_153249_1692`, which contains only `karpathy_only` results. Generated SQLite databases, Python caches, and pytest caches are intentionally ignored.

## Install

Option A: Claude Code plugin

```text
/plugin marketplace add AnamKwon/programming-as-theory-building-skill
/plugin install programming-as-theory-building-skill@programming-as-theory-building-skill
```

For a fork, replace `AnamKwon` with the account or organization that publishes the repository. The install command is `<plugin-name>@<marketplace-id>`; this repository uses `programming-as-theory-building-skill` for both.

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

From the parent experiment workspace, run 10-repeat sets and aggregate the comparable three-arm results:

```bash
MODEL=haiku REPEATS=10 ARMS="skills_off karpathy_only theory_only" ./run_skill_codegen_experiment.sh
MODEL=opus ./run_opus_code_review_experiment.sh .skill-codegen-runs/<run_id>
```

The published summary combines four complete 10-repeat review sets. A fresh `REPEATS=40` run can produce the same sample size, but it will not reproduce the exact copied run ids.

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
|   |-- marketplace.json
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
