# Programming as Theory Building Skill Promotion Guide

## Positioning

This skill is not a generic "write cleaner code" prompt. It is an operating rule set that asks a coding agent to recover the program's theory before changing code.

Main message:

> Most coding-agent failures are not syntax failures. They are theory failures.

Short description:

> A Claude Code skill that helps coding agents preserve program theory before changing code.

Direct problem statement:

> Stop coding agents from producing plausible patches that ignore your system's real invariants.

## Benchmark Talking Points

Use the 20-run-per-arm result.

- Code generation: Claude Code `MODEL=haiku`
- Review: Claude Opus
- Arms: `skills_off`, `karpathy_only`, `theory_only`
- Repeats: 20 per arm, 60 reviewed projects
- Task: FastAPI + SQLite inventory reservation/order orchestration API

Key numbers:

- `skills_off`: weighted total 70.2, functional correctness 59.7, good verdict 5/20
- `karpathy_only`: weighted total 72.1, functional correctness 59.8, good verdict 7/20
- `theory_only`: weighted total 77.8, functional correctness 69.2, good verdict 12/20

Safe interpretation:

> In this benchmark, the theory-only arm shifted the distribution toward better functional correctness. The result is not proof of universal superiority, but it is a useful signal that theory-recovery instructions can improve agent behavior on domain-heavy code generation tasks.

Avoid claiming:

- It always writes better code.
- It is universally better than Karpathy-style guidelines.
- It perfectly implements Naur's paper.
- Haiku results automatically generalize to every model.

## GitHub

Repository description:

```text
Claude Code skill that applies Naur's Programming as Theory Building to coding-agent workflows.
```

Recommended GitHub topics:

- `claude-code`
- `claude-plugin`
- `ai-coding`
- `coding-agent`
- `code-generation`
- `programming-as-theory-building`
- `software-engineering`
- `developer-tools`

Optional topics:

- `ai-assisted-programming`
- `llm`
- `llm-agents`
- `benchmark`
- `prompt-engineering`
- `code-review`
- `refactoring`
- `peter-naur`

## X / Twitter

Post draft:

```text
Most coding-agent failures are not syntax failures.
They are theory failures.

I built a Claude Code skill based on Peter Naur's "Programming as Theory Building".

In a 60-project Haiku benchmark, theory-only improved:
- weighted score: 70.2 -> 77.8 vs no skills
- functional correctness: 59.7 -> 69.2
- good verdicts: 5/20 -> 12/20
```

Recommended hashtags:

```text
#ClaudeCode #AICoding #CodingAgents #SoftwareEngineering
```

Optional hashtags:

```text
#LLM #DevTools #CodeReview #Refactoring #PromptEngineering
```

Use 3-5 hashtags on X.

## LinkedIn

Post draft:

```text
I built a Claude Code plugin based on Peter Naur's "Programming as Theory Building."

The idea is simple: many coding-agent failures are not syntax failures. They are theory failures.

The agent writes code that looks plausible, but misses:
- the domain invariant,
- the reason the current boundary exists,
- the closest existing facility,
- the behavior that would prove correctness.

In a 60-project benchmark using Claude Haiku for generation and Claude Opus for review, the theory-only skill produced the strongest results across weighted score, functional correctness, and good-verdict count.

This is not a claim that one instruction file solves code generation. It is evidence that theory-recovery instructions can shift agent behavior in domain-heavy coding tasks.
```

LinkedIn hashtags:

```text
#SoftwareEngineering #AIEngineering #DeveloperTools #CodeGeneration #ClaudeCode
```

## Hacker News

Title candidates:

- `Show HN: A Claude Code skill based on Naur's Programming as Theory Building`
- `Show HN: Programming as Theory Building for Claude Code agents`
- `Show HN: A theory-building skill for coding agents`

General discussion title candidates:

- `I turned Programming as Theory Building into coding-agent instructions`
- `Benchmarking a theory-building skill for code generation`

Tone:

- Lead with the tool and benchmark.
- Say "I tried..." rather than making universal claims.
- Link the raw results in `benchmark/raw-results/`.

Avoid:

- `AI coding solved`
- `This beats all other prompting`
- `Karpathy guidelines are bad`

Ready-to-post Show HN body:

```md
I built a Claude Code plugin that turns Peter Naur's "Programming as Theory Building" into operating rules for coding agents.

The motivation is that many coding-agent failures are not syntax failures. The generated code can compile, look plausible, and sometimes even pass shallow tests while still missing the real theory of the program:

- what invariant the code is meant to protect,
- why the current boundary exists,
- where the change belongs,
- what behavior would actually prove correctness.

The plugin packages a Claude Code skill plus a `CLAUDE.md` version of the same rules. It asks the agent to recover the relevant theory before editing code, place changes beside the closest existing domain concept, avoid speculative abstractions, and verify behavior tied to the invariant.

I also included a small benchmark. The task was generating a FastAPI + SQLite inventory reservation/order orchestration API. Code generation used Claude Code `MODEL=haiku`; review used a separate Claude Opus pass with a weighted rubric.

20 runs per arm, 60 reviewed projects:

| Arm | Avg weighted total | Functional correctness | Good verdicts |
| --- | ---: | ---: | ---: |
| no skills | 70.2 | 59.7 | 5/20 |
| Karpathy-style guidelines only | 72.1 | 59.8 | 7/20 |
| theory-building skill only | 77.8 | 69.2 | 12/20 |

This is not meant as proof that the skill is universally better. The interesting signal is narrower: in this benchmark, forcing the agent to recover the program theory first shifted results toward better functional correctness.

Repo:
https://github.com/AnamKwon/programming-as-theory-building-skill

Raw extracted review results are included under:
`benchmark/raw-results/`

I would be interested in feedback on the rule design and on better benchmarks for testing whether an agent understands the program rather than just generating plausible code.
```

Short HN comment body:

```md
I built this after trying to turn Naur's "Programming as Theory Building" into practical instructions for coding agents.

The skill asks the agent to recover the domain invariant, explain the current code shape, place the change beside the closest existing facility, and verify behavior that actually proves correctness.

I included a small 60-project benchmark using Claude Haiku for generation and Claude Opus for review. The theory-only arm scored higher than no-skills and Karpathy-style guidelines on weighted total and functional correctness, but I am treating it as a signal rather than a universal claim.

Raw extracted review results are in `benchmark/raw-results/`.
```

HN posting cautions:

- Use `Show HN` only when the GitHub repo is public and install instructions are usable.
- Pair the ready-to-post body with a `Show HN:` title. Use the general discussion titles only if rewriting the body as a discussion post.
- Lead with the tool and benchmark, not with a long paper summary.
- State the benchmark limitations explicitly.
- Avoid claiming the skill "beats" other prompting approaches in general.
- Expect discussion around benchmark validity; point people to `benchmark/raw-results/`.

## Reddit

Subreddit candidates:

- `r/ClaudeAI`
- `r/programming`
- `r/softwaredevelopment`
- `r/LocalLLaMA` only if framed around agent prompting/benchmarks rather than Claude-specific install.

Title candidates:

- `I built a Claude Code skill from Naur's Programming as Theory Building`
- `Experiment: theory-recovery instructions for coding agents`
- `A small benchmark of no-skill vs Karpathy-style vs theory-building coding instructions`

Flairs:

- `Showcase`
- `Tool`
- `Discussion`
- `Benchmark`

Ready-to-post body:

```md
I built a small Claude Code plugin based on Peter Naur's "Programming as Theory Building."

The motivation is that a lot of coding-agent failures are not syntax failures. The code compiles, the files look plausible, and sometimes the tests even pass, but the generated change misses the actual theory of the program:

- What domain invariant is this code protecting?
- Why is the current boundary shaped this way?
- Which existing service/repository/module does this change most resemble?
- What behavior would prove the change is correct?

The skill turns those questions into operating rules for the agent before it edits code. It pushes the agent to inspect the relevant code path, place changes near the closest existing concept, avoid speculative abstractions, and verify behavior that matters rather than only syntax.

I also ran a small benchmark. The task was to generate a FastAPI + SQLite inventory reservation/order orchestration API. Code generation used Claude Code `MODEL=haiku`, and a separate Claude Opus review pass scored the generated projects.

20 runs per arm, 60 reviewed projects total:

| Arm | Avg weighted total | Functional correctness | Good verdicts |
| --- | ---: | ---: | ---: |
| no skills | 70.2 | 59.7 | 5/20 |
| Karpathy-style guidelines only | 72.1 | 59.8 | 7/20 |
| theory-building skill only | 77.8 | 69.2 | 12/20 |

The result I find interesting is not that this "solves" code generation. It does not. The theory-only arm still produced some bugs. But it shifted the distribution toward better functional correctness, which is exactly where coding agents tend to fail on domain-heavy tasks.

Repo:
https://github.com/AnamKwon/programming-as-theory-building-skill

Raw extracted review results are included under:
`benchmark/raw-results/`

I would be interested in feedback on two things:

1. Are these the right operating rules for coding agents, or would you phrase the theory-building checks differently?
2. What benchmark tasks would better test whether an agent understands the program rather than just producing plausible code?
```

Shorter Reddit body:

```md
I built a Claude Code plugin based on Peter Naur's "Programming as Theory Building."

The core idea: many coding-agent failures are not syntax failures. They are theory failures. The generated code looks plausible but misses the domain invariant, the reason the current boundary exists, or the behavior that would prove correctness.

The skill asks the agent to recover that theory before editing code:

- map the real-world invariant,
- explain the current shape,
- place the change beside the closest existing facility,
- avoid speculative abstractions,
- verify behavior that matters.

I ran a small 60-project benchmark using Claude Haiku for generation and Claude Opus for review. The theory-only arm scored highest on weighted total and functional correctness:

- no skills: 70.2 weighted / 59.7 correctness / 5 good verdicts out of 20
- Karpathy-style only: 72.1 weighted / 59.8 correctness / 7 good verdicts out of 20
- theory-only: 77.8 weighted / 69.2 correctness / 12 good verdicts out of 20

Repo:
https://github.com/AnamKwon/programming-as-theory-building-skill

Curious what people think: is "recover the program theory first" a useful instruction pattern for coding agents?
```

Posting cautions:

- On `r/programming`, emphasize the benchmark and raw result files.
- On `r/ClaudeAI`, emphasize that this is installable as a Claude Code plugin.
- On `r/LocalLLaMA`, frame it as an agent-instruction experiment rather than a Claude-specific install guide.
- Avoid "beats Karpathy" framing. Say the theory-only arm scored higher in this benchmark, while Karpathy-style guidance still slightly improved the no-skill baseline.
- Before posting, confirm the repository URL is public and accessible: `https://github.com/AnamKwon/programming-as-theory-building-skill`.

## Tag Strategy

GitHub topics should be specific for search:

```text
claude-code, claude-plugin, coding-agent, ai-coding, code-generation, programming-as-theory-building, software-engineering, developer-tools
```

Social hashtags should stay compact:

```text
#ClaudeCode #AICoding #CodingAgents #SoftwareEngineering
```

For benchmark-heavy posts:

```text
#CodeGeneration #LLM #CodeReview
```

For Naur/paper-heavy posts:

```text
#SoftwareEngineering #Programming
```

## Rollout Order

1. Set GitHub description and topics.
2. Publish an X/LinkedIn post with the 60-project benchmark numbers.
3. Submit a Show HN post with raw results linked.
4. Post to Reddit as an experiment and ask for feedback.
5. Add 2-3 real examples showing which coding-agent failures the skill prevents.
