# Benchmark Prompts

These are the human-readable code-generation prompts used by the published
benchmark families.

| Prompt family | Prompt file | Used by codegen runs |
| --- | --- | --- |
| `basic-commerce` | [basic-commerce.md](basic-commerce.md) | `20260609_152615_16568`, `20260609_195509_38196`, `20260610_091239_64934`, `20260610_092511_66275` |
| `strict-production` | [strict-commerce.md](strict-commerce.md) | `20260610_141237_92652`, `20260610_202937_24877` |
| `strict-commerce-no-mcp` | [strict-commerce.md](strict-commerce.md) | `20260611_002935_41179` |

The raw run folders also preserve per-run prompt copies under
`benchmark/raw-results/.skill-codegen-runs/<run_id>/<arm>/prompt_*.txt`.
Those copies include the exact prompt text submitted during each run. The files
here exist so readers can inspect the benchmark tasks without digging through
the raw result tree.
