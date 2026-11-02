# Model choice

The subject model for every recorded run is `claude-sonnet-5-5`.

## Prices

Prices are per million tokens (MTok), in US dollars, as verified on 2026-11-02 against the vendor pricing page [S101] and the models overview page [S102]. Prices change; re-check both pages before quoting these numbers, and record the date you checked.

| Model id | Role in this project | Input per MTok | Output per MTok | Cache hit per MTok | Notes |
|---|---|---|---|---|---|
| `claude-haiku-5-5` | Cost floor | $0.10 | $0.50 | $0.01 | Prompts up to 100,000 tokens. Prompts over 100,000 tokens cost $0.50 input and $2.50 output. |
| `claude-sonnet-5-5` | Subject | $2 | $10 | $0.10 | Flat price across the 1M-token context window. |
| `claude-opus-5-5` | Cost ceiling for comparison | $4 | $20 | $0.20 | Flat price across the 1M-token context window. |

Batch requests are listed at 50% off and are not used for interactive agent runs. The pricing page also lists a higher tier (`claude-fable-5-1`, $10 input and $50 output) positioned for demanding long-horizon work; it is out of scope here and is noted only so the ceiling above is not mistaken for the most expensive option on the page.

## Why this model

- It is the everyday coding workhorse of the current line-up: the models overview page positions it as the best balance of speed and intelligence, while the dearer tier is positioned for long-running agentic coding [S102].
- It costs half of `claude-opus-5-5` per token on both input and output ($2 versus $4 input, $10 versus $20 output) [S101]. That is cheap enough to run many graded runs per task, which this project needs because a single run proves little and variance across runs is part of the evidence.
- It is the model a typical developer is most likely to run day to day, so behaviours recorded here generalise to ordinary use better than results from the most expensive tier would.
- `claude-haiku-5-5` is the cost floor: at $0.10 and $0.50 it is twenty times cheaper per token than the subject, but its own page positions it for high-volume, latency-sensitive work such as classification and routing rather than multi-step coding [S102], and its price rises fivefold once a prompt passes 100,000 tokens, which long agent sessions can reach [S101].
- `claude-opus-5-5` is the ceiling: if a behaviour appears on the subject, a later comparison run on the dearer tier shows whether money alone removes it.

## Cost per run, worked example

A run that reads 400,000 input tokens (most of it cache hits on a long session) and writes 20,000 output tokens is not priced from the headline numbers alone; the ledger records `input_tokens`, `cache_read_tokens`, `cache_creation_tokens` and `output_tokens` separately so that `cost_usd` can be recomputed. With no caching, 400,000 input and 20,000 output tokens on the subject would cost 0.4 × $2 + 0.02 × $10 = $1.00. Cache reads at $0.10 per MTok make the real figure much lower, which is why cache counters are mandatory ledger fields.

## Sources

- [S101] Pricing, vendor platform documentation, https://platform.claude.com/docs/en/about-claude/pricing, undated page, accessed 2026-11-02.
- [S102] Models overview, vendor platform documentation, https://platform.claude.com/docs/en/about-claude/models/overview, undated page, accessed 2026-11-02.

Both pages appear in `docs/sources.json` with the same URLs.
