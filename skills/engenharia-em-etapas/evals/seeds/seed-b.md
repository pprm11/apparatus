# Seed B: LLM gateway with model A/B (test seed, not a real task)

Use the skill `engenharia-em-etapas` to do this task.

Quero entender onde e como colocar um gateway de LLM na frente da Ariadne v2 que faça fallback entre modelos quando o principal falhar e permita A/B de modelo por lead (um lead fica sempre no mesmo modelo). Hoje a v2 chama o `llm.example.com` direto. Faz o domínio do problema primeiro e me manda as perguntas pro Dana e pro Pat. Depois faz o resto da série: as-is, mercado com benchmarks, solução, HLA com custo em 1-3-1 decidindo, e HLD. Pode fazer POC.

Não pode: deploy, criar recurso, mudar config, commit, push, PR, mensagem. Só leitura. Sem segredo impresso.

Setup for this test run:
- Repository: the current folder is a checkout of `acme-org/ariadne`. Read code only at commit `9518005` (`git show 9518005:<path>`).
- The as-is may use files and public documentation only. No live checks against any cloud, database or API in this test: write NOT VERIFIED where a live check would be needed, with the command that would verify it.
- Write every output under `skill-test/` in the current folder. Do not touch any other file.
- Owner answers: when your problem domain draft lists its questions for the owners, and only then, read `answers-b.md` (next to this seed, path given in your task message). Those are simulated owner answers for this test. Apply them as the skill says.
- Prices: the AWS public price list JSON files may be downloaded with curl from `https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/<Service>/current/sa-east-1/index.json` into `skill-test/prices/`.
- When done, write `skill-test/REPORT.md`: what you produced, what you could not do, and every place where the skill's instructions were unclear or missing.
