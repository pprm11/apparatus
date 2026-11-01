# Brief: correctness review (is the design right, not is it well written)

Scratchpad root (R): <scratchpad>
Series (read-only for you): <home>\Codes\ariadne\docs\rfcs\conversation-routing-*.md
Team decisions (the source, never contradict them; a conflict is a finding for the owners): R\v3\decisions-r3.md and R\v3\decisions-r4.md
Code read at commit 9518005 of the repo <home>\Codes\ariadne (`git -C <home>\Codes\ariadne show 9518005:<path>`).
POC code and outputs: R\poc\
AWS price list files: R\prices\

The series designs a Router (AWS API Gateway HTTP API + Lambda Python + one DynamoDB table, sa-east-1) in front of Relay that splits Ariadne sales conversations between v1 (stable) and v2 (canary), with sticky 30-day Assignments, kills, owner lookup, end on sale, pin, stages 0, 5, 10, 25, 50, 100 percent.

Your job is adversarial: find where the design is WRONG, not where the text is unclear. Readability, style and typos are out of scope. Assume the authors were careful and look for what they missed.

## What counts as a finding

- A requirement or invariant the design does not actually guarantee: give a concrete counterexample (an interleaving of events, a failure, an input) and the step where it breaks.
- A claim about a platform (AWS, DynamoDB, API Gateway, Lambda, GupShup, Relay, mermaid not included) that is false or unverified and matters: check the official documentation with WebFetch and cite URL and access date 28/10/2026.
- A number that does not follow from its inputs: recompute it (cost, capacity, sample size, latency budget, timeouts) and show the computation.
- A missing failure mode, race, security hole, privacy leak, or operational trap with real impact.
- An internal contradiction between stages that changes behaviour.
- A test or POC that cannot fail, or does not prove what it claims.

Prefer executable evidence: write and run small scripts or tests under R\correctness\<your-area>\ (Python is available; pip install with `--target` into that folder if you need a package). Do not edit the series, the POC folder or any repository.

## Output: R\correctness\<your-area>.md

A table: Id (your prefix + number) · Severity (blocking: the system would misbehave or the decision is wrong; major: likely bug or unsafe gap; minor: edge case) · Where (file and section, ID) · Finding · Evidence (counterexample, computation, doc quote with URL, or script and its output) · Proposed fix (the smallest design change; if it touches a team decision, say "question for the owners" instead).
Then "Checked and correct": the important things you verified hold, one line each, with how you verified them (so we know what was covered).

Final message: at most 15 lines: counts by severity, the blocking findings in one line each, and what you verified as correct.
