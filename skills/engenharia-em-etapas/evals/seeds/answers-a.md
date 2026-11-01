# Simulated owner answers for seed A (test only, not real decisions)

Answers given on 28/10/2026 by the owners named in the test (tech lead "Dana", business owner "Pat", platform team). Treat them as team decisions dated 28/10/2026.

1. Rate limit: the GupShup line allows 80 messages per second in bursts and 1,000 per minute sustained (platform team, from the GupShup console). Treat as a fact with that source.
2. Volume: about 3,250 new leads a day; templates and follow-ups are about 2.1 outbound messages per lead per day on average, peak hour 15 percent of the day (Pat).
3. Duplicates: a lead must never get the same template twice within 24 hours, whichever version sends it (Pat).
4. Ordering: messages to one lead must leave in the order they were requested (Dana).
5. Hosting: AWS sa-east-1 preferred; Railway stays for the v2 agent only (Dana).
6. Latency: a follow-up may leave up to 5 minutes after it was requested; an answer inside a live conversation does not go through this service (Dana).
7. Failure: if GupShup is down, messages wait up to 6 hours and then are dropped and logged (Pat).
8. Owner in production: Sam.
9. Observability: traces to LangWatch, like v1 (Dana).
10. Anything else not answered here stays an open question with an owner.
