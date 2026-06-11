# Programming as Theory Building Skill Promotion Guide

## Core Message

Most coding-agent failures are not syntax failures. They are theory failures:
the code looks plausible, but misses the domain invariant, the current boundary,
or the behavior that would prove correctness.

This skill turns Peter Naur's "Programming as Theory Building" into operating
rules for coding agents:

- map the domain rule,
- explain why the current code is shaped this way,
- place the change beside the closest existing facility,
- verify behavior that protects the invariant.

## Benchmark Angle

Use this framing when promoting the benchmark:

> The first benchmark used a loose `basic-commerce` prompt, so one fair criticism
> was that a theory-building skill had more room to help. I retested with a much
> more structured production prompt. Better prompts improved every arm, but the
> theory-building skill still led the structured prompt aggregate. A later strict
> no-MCP run also led, but it should be treated separately because the execution
> environment changed.

Key facts:

- Code generation: Claude Code `MODEL=haiku`
- Review: Claude Opus
- Parsed isolated reviews: 207
- Arms: `skills_off`, `karpathy_only`, `theory_only`
- Task: FastAPI + SQLite inventory reservation/order orchestration API

Prompt-family results:

| Prompt family | No skills | Comparison-guidelines only | Theory-building only |
| --- | ---: | ---: | ---: |
| `basic-commerce` | 71.0 | 73.9 | **77.9** |
| `strict-production` | 80.9 | 82.5 | **83.4** |
| `strict-commerce-no-mcp` separate environment | 78.5 | 84.6 | **88.5** |
| all parseable isolated reviews | 74.8 | 77.7 | **81.0** |

Safe takeaway:

> This is not "skills replace good prompts." It is: write the best structured
> prompt you can, then use theory-building rules to make the agent preserve those
> requirements in code, tests, and verification.

Avoid claiming:

- The skill is universally better.
- It always writes correct code.
- It beats every other coding-agent instruction style.
- The benchmark generalizes to every model or task.

## One-Liners

```text
Most coding-agent failures are not syntax failures. They are theory failures.
```

```text
I tested whether "recover the program theory first" still helps after the prompt is already structured. In this benchmark, it did.
```

```text
Good prompts help. Theory-building rules helped the agent preserve those prompt requirements in code, tests, and verification.
```

```text
The goal is not prettier generated code. It is code that preserves the domain invariant it was asked to implement.
```

```text
This Claude Code skill asks the agent to understand the program before changing it.
```

## X / Twitter

Short post:

```text
Most coding-agent failures are not syntax failures.
They are theory failures.

I retested my Claude Code theory-building skill after replacing a loose benchmark prompt with a structured one.

Better prompts improved every arm.
Theory-building still led: 83.4 vs 80.9 no skills.
```

Benchmark follow-up post:

```text
Earlier loose prompt:
theory-building 77.9 vs 71.0 no skills.

Structured prompt:
83.4 vs 80.9.

Separate strict no-MCP run:
88.5 vs 78.5.
(Different environment; not a pure prompt comparison.)

Takeaway: good prompts help, but theory-recovery rules can still improve domain-heavy code generation.
```

Thread starter:

```text
I wanted to test a fair criticism of my coding-agent skill:

"Maybe it only helped because the original prompt was too loose."

So I reran the benchmark with a much more structured production prompt: exact endpoints, status codes, error bodies, auth behavior, stock restoration, reservation expiry, and pagination.
```

Thread follow-up:

```text
The structured prompt improved every arm.

That matters. This is not a "skills replace good prompts" result.

But the theory-building skill still scored highest in the structured prompt family:

no skills: 80.9
Comparison-guidelines only: 82.5
(compact coding-style baseline)
theory-building only: 83.4
```

Thread close:

```text
My takeaway:

Write the best structured prompt you can.

Then give the agent operating rules that force it to preserve those requirements as program theory: invariants, boundaries, existing facilities, and behavior-proving tests.
```

Recommended hashtags:

```text
#ClaudeCode #AICoding #CodingAgents #SoftwareEngineering
```

## Reddit

Title candidates:

- `I tested whether theory-recovery instructions still help after the prompt is already structured`
- `A small benchmark: no skills vs Comparison-guidelines only vs Programming as Theory Building`
- `I built a Claude Code skill from Naur's Programming as Theory Building`
- `Experiment: can coding agents preserve program theory better?`

Short body:

```md
I built a Claude Code skill based on Peter Naur's "Programming as Theory Building."

The idea is simple: many coding-agent failures are not syntax failures. The code compiles and looks plausible, but it misses the domain invariant, the reason a boundary exists, or the behavior that would actually prove correctness.

One fair criticism of my first benchmark was that the original `basic-commerce` prompt was loose. It asked for a FastAPI + SQLite inventory reservation/order API, but left many details implicit. That gives a theory-building skill more room to help.

So I tested again with a much more structured production prompt: exact endpoints, status codes, error bodies, 300-second reservation expiry, stock deduction/restoration, auth behavior, and pagination semantics. I also report a later strict no-MCP run separately because the prompt stayed strict but the execution environment changed.

Results:

| Prompt family | no skills | Comparison-guidelines only | theory-building only |
| --- | ---: | ---: | ---: |
| loose `basic-commerce` | 71.0 | 73.9 | **77.9** |
| structured `strict-production` | 80.9 | 82.5 | **83.4** |
| strict no-MCP run, separate environment | 78.5 | 84.6 | **88.5** |

My takeaway is not "skills replace good prompts." Better prompt structure improved every arm.

The useful signal is narrower: after the prompt became explicit, theory-building instructions still helped the agent preserve requirements in code, tests, and verification. The no-MCP result is supporting evidence from a related but not identical environment.

Repo:
https://github.com/AnamKwon/programming-as-theory-building-skill

Raw review results are included under `benchmark/raw-results/`.

Curious what people think: is "recover the program theory first" a useful instruction pattern for coding agents?
```

More discussion-oriented body:

```md
I have been experimenting with coding-agent instructions based on Naur's "Programming as Theory Building."

The skill asks the agent to answer a few checks before non-trivial code work:

- What domain rule or invariant maps to this code?
- Why is the current code shaped this way?
- Which existing facility does this change most resemble?
- What behavior would prove the implementation is correct?

The interesting benchmark result was not the first loose prompt. That setup was arguably favorable to the skill because the prompt left many business rules implicit.

The more useful result came after rewriting the task as a structured production prompt. All arms improved, which is exactly what I would expect from a better prompt. But the theory-building arm still led the structured aggregate, and a later strict no-MCP run led in a separate environment.

So the claim is modest: this does not prove universal superiority. It suggests that theory-recovery rules can complement structured prompts on domain-heavy code generation tasks.
```

Subreddit notes:

- `r/ClaudeAI`: emphasize installability as a Claude Code skill/plugin.
- `r/programming`: emphasize benchmark limits and raw results.
- `r/softwaredevelopment`: emphasize invariants, boundaries, and behavioral tests.
- `r/LocalLLaMA`: frame it as an instruction-pattern experiment, not a Claude-only tool.

### Reddit Repost With `code-assistant-peers`

Use this when reposting the skill benchmark and also mentioning the peer-review
MCP without making the post feel like two unrelated promotions.

Repost title candidates:

- `Follow-up: theory-building prompts are useful, but I also wanted a review gate`
- `Structured prompts help. I also wanted coding agents to review each other's patches`
- `Follow-up tool: an MCP peer-review gate for Claude Code, Codex, and adapter-supported CLIs`

Repost body:

```md
I previously shared a small benchmark for a Claude Code skill based on Naur's "Programming as Theory Building."

The short version: the first loose commerce prompt gave the skill more room to help, so I retested with a structured production prompt. Better prompt structure improved every arm, but the theory-building arm still led the structured aggregate.

That solved one side of the problem: getting the coding agent to preserve the program theory while writing code.

The other side is review.

Even with better instructions, the same agent that wrote a patch can miss its own assumptions. So I also built `code-assistant-peers`, an MCP server for local peer review between coding assistants.

The workflow is:

- one assistant implements the change,
- another assistant reviews the diff,
- findings are saved locally,
- the host assistant is pushed to run a post-edit review gate before giving the final answer.

It supports Claude Code and Codex out of the box, with adapters for Gemini and other prompt-capable CLIs.

So the two tools fit together like this:

- `programming-as-theory-building-skill`: make the implementing agent recover invariants before editing.
- `code-assistant-peers`: make a separate agent check the patch before you trust it.

Skill repo:
https://github.com/AnamKwon/programming-as-theory-building-skill

MCP review gate:
https://github.com/AnamKwon/code-assistant-peers
```

Short comment version:

```md
Related tool I built after this benchmark:

`code-assistant-peers` is an MCP review gate for coding agents. Claude Code and Codex work out of the box; adapter-supported CLIs such as Gemini can join the review flow. Findings are stored locally, and the host assistant is prompted to run the review gate before the final answer.

The theory-building skill is about writing code with the right invariants. This MCP is about not letting the same agent be the only reviewer of its own patch.

https://github.com/AnamKwon/code-assistant-peers
```

Very short P.S.:

```md
P.S. I also built a companion MCP review gate: `code-assistant-peers`.

It lets one CLI coding agent write the patch and another review it before the final answer, with review rounds/findings stored locally.

https://github.com/AnamKwon/code-assistant-peers
```

Positioning cautions:

- Do not make the repost only about the MCP; anchor it as the review-side
  complement to the theory-building skill.
- Avoid implying peer review guarantees correctness. Say it catches assumptions
  and creates a repeatable review gate.
- Mention that Claude Code and Codex work out of the box; mention Gemini and
  other CLIs as adapter-supported rather than identical first-class defaults.

## LinkedIn

Concise post:

```text
I built a Claude Code skill based on Peter Naur's "Programming as Theory Building."

The premise: many coding-agent failures are not syntax failures. They are theory failures. The generated code looks plausible, but misses the domain invariant, the existing boundary, or the behavior that would prove correctness.

One weakness in my first benchmark was that the original commerce prompt was loose. That gave the skill more implicit theory to recover.

So I retested with a structured production prompt that specified endpoints, status codes, error bodies, reservation expiry, stock restoration, authentication, and pagination. I also report the later strict no-MCP run separately because the environment changed.

The structured prompt improved every arm. That is the important baseline.

But the theory-building arm still scored highest:

- loose prompt: 77.9 vs 71.0 no skills
- structured prompt: 83.4 vs 80.9 no skills
- strict no-MCP run, separate environment: 88.5 vs 78.5 no skills

The takeaway is not that instructions replace good prompts. It is that structured prompts and theory-recovery rules solve different parts of the problem.

A good prompt states the requirements. Theory-building rules push the agent to preserve those requirements in code, tests, and verification.
```

Hashtags:

```text
#SoftwareEngineering #AIEngineering #DeveloperTools #CodeGeneration #ClaudeCode
```

## Hacker News

Title candidates:

- `Show HN: Programming as Theory Building for Claude Code agents`
- `Show HN: A Claude Code skill based on Peter Naur's theory-building idea`
- `I tested theory-recovery instructions for coding agents`

Short Show HN body:

```md
I built a Claude Code plugin that turns Peter Naur's "Programming as Theory Building" into operating rules for coding agents.

The plugin asks the agent to recover the domain invariant, explain the current code shape, place the change beside the closest existing facility, avoid speculative abstractions, and verify behavior that proves correctness.

I also included a small benchmark on a FastAPI + SQLite inventory reservation/order orchestration task. Generation used Claude Code `MODEL=haiku`; review used Claude Opus with a weighted rubric.

One fair criticism of the first benchmark was that the original `basic-commerce` prompt was loose, so the theory-building skill had more implicit behavior to recover. I added a structured prompt family to test that, and I report the later strict no-MCP run separately because the execution environment changed.

| Prompt family | no skills | Comparison-guidelines only | theory-building only |
| --- | ---: | ---: | ---: |
| `basic-commerce` | 71.0 | 73.9 | 77.9 |
| `strict-production` | 80.9 | 82.5 | 83.4 |
| `strict-commerce-no-mcp`, separate environment | 78.5 | 84.6 | 88.5 |

The structured prompt improved every arm, so I am not claiming that skills replace prompt quality. The narrower signal is that theory-recovery instructions still helped after the prompt became explicit. The no-MCP result is related evidence, not a pure prompt-structure comparison.

Repo:
https://github.com/AnamKwon/programming-as-theory-building-skill

Raw extracted review results are under `benchmark/raw-results/`.
```

HN cautions:

- Keep the benchmark-limitation paragraph in the post.
- Avoid "AI coding solved" language.
- Do not frame it as "other coding guidelines are bad"; they improved the baseline.
- Link raw results so people can inspect the runs.

## GitHub

Repository description:

```text
Claude Code skill that applies Naur's Programming as Theory Building to coding-agent workflows.
```

Short README badge-style tagline:

```text
Recover the program theory before changing the code.
```

Topics:

```text
claude-code, claude-plugin, ai-coding, coding-agent, code-generation, programming-as-theory-building, software-engineering, developer-tools, benchmark, prompt-engineering
```

## Product Hunt / Dev Tools Communities

Short launch copy:

```text
Programming as Theory Building Skill is a Claude Code plugin that makes coding agents recover the program's domain theory before editing code.

It asks the agent to map invariants, explain existing boundaries, place changes by similarity, avoid speculative abstractions, and verify behavior that matters.

In a small Claude Haiku + Opus benchmark, structured prompts improved every arm, but the theory-building skill still led the structured prompt aggregate. A later strict no-MCP run also led, with the environment change reported separately.
```

Ultra-short copy:

```text
A Claude Code skill for coding agents that need to preserve business invariants, not just generate plausible files.
```

## Korean Summary For Yourself

```text
이전 basic-commerce 벤치마크는 프롬프트가 느슨해서 theory-building skill에 유리할 수 있었다.
그래서 endpoint/status/error/expiry/auth/pagination 등을 명시한 structured prompt로 다시 테스트했다.
좋은 프롬프트는 모든 arm의 점수를 올렸다.
그럼에도 theory-building arm이 structured prompt aggregate에서도 가장 높은 점수를 냈다.
strict-commerce-no-mcp는 프롬프트는 같지만 실행 환경이 달라 별도 근거로만 다룬다.
따라서 메시지는 "스킬이 좋은 프롬프트를 대체한다"가 아니라,
"좋은 프롬프트 + 프로그램 이론을 보존하게 만드는 운영 규칙"이 더 강하다는 것이다.
```

## Rollout Order

1. Confirm the GitHub repo is public and install instructions work.
2. Update GitHub description and topics.
3. Post the short X version.
4. Post the Reddit short body in `r/ClaudeAI` or `r/softwaredevelopment`.
5. Use the HN body only after raw benchmark files are easy to inspect.
