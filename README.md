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

The benchmark compares commerce-backend code generation across three isolated arms:

- `skills_off`: managed Claude Code skills disabled.
- `karpathy_only`: only the Karpathy guidelines skill enabled.
- `theory_only`: only this Programming as Theory Building skill enabled.

Code generation used **Claude Haiku** through the Claude Code `MODEL=haiku` setting for every arm. Each generation ran in a fresh temporary workspace, and generated projects were reviewed by a separate Claude Opus review pass using `benchmark-codegen-review-v1`.

The copied benchmark now contains two prompt families:

- `basic-commerce`: the original, looser FastAPI + SQLite inventory reservation/order orchestration prompt.
- `strict-production`: a later, more explicit prompt that specifies endpoints, status codes, error bodies, expiration behavior, stock restoration, 401 auth behavior, and pagination semantics.

Because the prompt changed, the headline result is reported by prompt family rather than as one flattened average.

| Prompt family | Arm | n | Avg weighted | Functional | Executability | Test quality | Verdict summary |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| `basic-commerce` | `skills_off` | 40 | 71.0 | 61.4 | 68.9 | 65.8 | 12 good, 27 mixed, 1 poor |
| `basic-commerce` | `karpathy_only` | 40 | 73.9 | 63.8 | 71.0 | 70.5 | 19 good, 21 mixed |
| `basic-commerce` | `theory_only` | 40 | **77.9** | **68.6** | **78.5** | **76.1** | 27 good, 13 mixed |
| `strict-production` | `skills_off` | 19 | 80.9 | 76.6 | 74.2 | 80.3 | 4 excellent, 7 good, 8 mixed |
| `strict-production` | `karpathy_only` | 19 | 82.5 | 77.5 | **80.5** | 83.2 | 5 excellent, 5 good, 9 mixed |
| `strict-production` | `theory_only` | 20 | **83.4** | **81.8** | 77.8 | **83.8** | 4 excellent, 12 good, 4 mixed |

## Interpreting the result

The `basic-commerce` prompt is the cleaner test of skill behavior because the prompt leaves more program theory to be inferred. In that family, `theory_only` won all four run-level comparisons. Its advantage was strongest in executability and tests, where it led `skills_off` by +9.6 and +10.3 points respectively.

The `strict-production` prompt raised every arm. It explicitly supplied many rules that the theory-building skill otherwise had to recover: status codes, stock restoration, expiration behavior, idempotency expectations, and pagination semantics. In that stricter family, the gap narrowed; `karpathy_only` won one run and `theory_only` won the other.

The overall pattern is that `karpathy_only` improves readability and compactness, while `theory_only` more consistently improves domain correctness, executability, and behavioral tests. Neither skill eliminates recurring failures by itself: inventory/reservation invariants, idempotency, expiration/state transitions, SQLite isolation, runtime entrypoints, dead code, and README overclaims still appear in reviews.

Run-by-run results, invalid review-output notes, copied raw result folders, and recurring failure categories are documented in [benchmark/README.md](benchmark/README.md).

- `benchmark/results-20260609.json`
- `benchmark/raw-results/.skill-codegen-runs/`
- `benchmark/raw-results/.skill-review-runs/`

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

From the parent experiment workspace, run 10-repeat sets and aggregate results by prompt family:

```bash
MODEL=haiku REPEATS=10 ARMS="skills_off karpathy_only theory_only" ./run_skill_codegen_experiment.sh
MODEL=opus ./run_opus_code_review_experiment.sh .skill-codegen-runs/<run_id>
```

The published benchmark combines multiple 10-repeat batches. Keep prompt revisions separate when aggregating; the `basic-commerce` and `strict-production` prompts are not directly interchangeable samples.

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
