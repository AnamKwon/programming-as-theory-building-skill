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
