# Programming as Theory Building Skill

A Claude Code plugin and reusable coding-agent skill that turns code generation from prompt completion into theory-preserving engineering work.

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

Code generation used **Claude Haiku** through the Claude Code `MODEL=haiku` setting for every arm. Each arm ran 10 independent generations in a fresh temporary workspace. The generated projects were then reviewed by a separate Claude Opus review pass using a weighted rubric for task fulfillment, functional correctness, executability, test quality, code quality, minimality, and security/safety.

Latest 3-arm run used:

- Codegen run: `.skill-codegen-runs/20260609_195509_38196`
- Review run: `.skill-review-runs/20260609_231224_49469`
- Codegen model setting: `MODEL=haiku`
- Repeats: 10 per arm, 30 total generated projects
- Prompt: FastAPI + SQLite inventory reservation and order orchestration API
- Reviewer rubric: `benchmark-codegen-review-v1`

| Arm | Avg weighted total | Functional correctness | Test quality | Good verdicts | Mixed verdicts |
| --- | ---: | ---: | ---: | ---: | ---: |
| `skills_off` | 73.7 | 60.7 | 73.0 | 4/10 | 6/10 |
| `karpathy_only` | 72.0 | 56.5 | 71.0 | 4/10 | 6/10 |
| `theory_only` | 76.7 | 67.7 | 74.7 | 6/10 | 4/10 |

The largest difference was not formatting or surface completeness. `theory_only` improved the reviewer-scored correctness of the generated business rules: stock availability, idempotency, reservation expiration, order state transitions, and error behavior. It also produced the highest average code quality and security/safety scores in this run.

## Interpreting the result

The baseline without skills was already capable of producing complete-looking FastAPI projects, but the review repeatedly found hidden domain failures: tests passing while stock was not actually reserved, order state transitions diverging from reservation state, or generated code leaving committed database artifacts and unused schemas.

The Karpathy-only arm was useful as general coding discipline, but in this benchmark it did not outperform the baseline. Its average score was slightly lower than `skills_off`, with similar verdict distribution. The pattern in review findings suggests that broad "good code" guidance can still miss the exact invariant unless the agent is forced to rebuild the program's domain theory.

The theory-only arm was not perfect. Review still found oversell, expiration, and validation bugs in some runs. The useful signal is that it shifted the distribution: more `good` verdicts, higher average functional correctness, and clearer service/repository/API boundaries tied to the requested workflow.

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

From the parent experiment workspace:

```bash
MODEL=haiku REPEATS=10 ARMS="skills_off karpathy_only theory_only" ./run_skill_codegen_experiment.sh
MODEL=opus ./run_opus_code_review_experiment.sh .skill-codegen-runs/<run_id>
```

The benchmark harness intentionally keeps `both` out of the default comparison set. `ARMS=both` remains available as an explicit opt-in, but the default comparison isolates single-skill effects.

## Citation

Naur, Peter. "Programming as Theory Building." *Microprocessing and Microprogramming*, vol. 15, no. 5, 1985, pp. 253-261.

## Repository layout

```text
.
|-- README.md
|-- LICENSE
|-- CITATION.cff
|-- CLAUDE.md
|-- .claude-plugin/
|   `-- plugin.json
|-- benchmark/
|   |-- README.md
|   `-- results-20260609.json
|-- skills/
|   `-- programming-as-theory-building/
|       `-- SKILL.md
`-- .gitignore
```
