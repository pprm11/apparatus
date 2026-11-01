# Seed A: outbound message queue (test seed, not a real task)

Use the skill `engenharia-em-etapas` to do this task.

Investiga onde deve rodar um serviço de envio outbound da Ariadne (templates e follow-ups) que a v1 e a v2 vão compartilhar durante o canary. Hoje cada versão manda direto pro GupShup e a linha tem limite de taxa; com as duas mandando ao mesmo tempo, a gente pode estourar o limite ou mandar duas mensagens pro mesmo lead. Escreve a série inteira: domínio do problema, as-is, estudo de mercado, domínio da solução, HLA e HLD. Analisa custo, faz 1-3-1 e decide. Avalia tecnologias e decide. Pode fazer POCs pra testar os conceitos.

Não pode: deploy, criar recurso de nuvem, mudar config, commit, push, abrir PR, mandar mensagem pra ninguém. Só leitura em todo sistema. Não imprime segredo.

Setup for this test run:
- Repository: the current folder is a checkout of `acme-org/ariadne`. Read code only at commit `9518005` (`git show 9518005:<path>`).
- The as-is may use files and public documentation only. No live checks against any cloud, database or API in this test: write NOT VERIFIED where a live check would be needed, with the command that would verify it.
- Write every output under `skill-test/` in the current folder. Do not touch any other file.
- Owner answers: when your problem domain draft lists its questions for the owners, and only then, read `answers-a.md` (next to this seed, path given in your task message). Those are simulated owner answers for this test. Apply them as the skill says.
- Prices: the AWS public price list JSON files may be downloaded with curl from `https://pricing.us-east-1.amazonaws.com/offers/v1.0/aws/<Service>/current/sa-east-1/index.json` into `skill-test/prices/`.
- When done, write `skill-test/REPORT.md`: what you produced, what you could not do, and every place where the skill's instructions were unclear or missing.
