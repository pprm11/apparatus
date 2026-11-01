# prompts/

Prompt texts for the unattended model passes. The scripts fill the `{{PLACEHOLDERS}}` and pass the result to a
model.

- `harvest.md`: turns one archived session into a memory or a skill draft (`harvest.sh`).
- `weekly-maintenance.md`: the weekly lint and compile pass over the ego memory (`weekly.sh`).
- `learn-classify.md` and `learn-propose.md`: the two steps of the self-learning loop (`tools/learn.py`).

Session text inside a prompt is data, never instructions. Keep each prompt short and tool-neutral.
