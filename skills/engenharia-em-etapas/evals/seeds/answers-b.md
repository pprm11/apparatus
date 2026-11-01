# Simulated owner answers for seed B (test only, not real decisions)

Answers given on 28/10/2026 by the owners named in the test (tech lead "Dana", business owner "Pat"). Treat them as team decisions dated 28/10/2026.

1. Fallback: when the primary model errors or exceeds 20 s, retry once on the fallback model; a turn may never be answered by two models (Dana).
2. A/B: a lead keeps its model for 30 days after its last message; the share of the challenger model starts at 10 percent (Pat).
3. What counts as success for the A/B: handoff rate and priced-lead rate per model, same criteria as the canary of the router (Pat).
4. Hosting: inside the v2 process is acceptable if it does not add more than 50 ms; otherwise AWS sa-east-1 (Dana).
5. Data: prompts and answers must not leave Brazil-hosted or contracted providers; no prompt logging outside LangWatch (Dana).
6. Volume: about 3,250 leads a day at 7.75 turns per lead (from `docs/capacidade-e-rollout.md:30-35` at commit 9518005).
7. Cost ceiling: the gateway itself must cost under 100 dollars a month at today's volume, model tokens excluded (Pat).
8. Owner in production: Sam.
9. Anything else not answered here stays an open question with an owner.
