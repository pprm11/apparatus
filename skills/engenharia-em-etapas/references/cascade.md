# Cascata: quando a fonte muda

Use quando o domínio do problema, uma decisão do time ou um fato do as-is mudar, ou quando o usuário disser "repensa as etapas seguintes".

1. Backup da revisão atual e cópia de trabalho (`rN/new/`, `rN/base/`). Grave no arquivo de decisões tudo que foi decidido na conversa desde a última rodada.
2. Mostre o plano (telinha) e pergunte como tratar as decisões: A) o agente decide o reversível de design e lista cada mudança com motivo, decisão do time vira pergunta; B) menu 1-3-1 ao fim de cada etapa.
3. Uma etapa por vez, em ordem (1 → 6), um subagente Sonnet por etapa com o brief [cascade-brief](cascade-brief.md). Cada um entrega: a etapa revisada, `trace-<etapa>.md` (covered, stale, missing, contradicts, orphan) e `changes-<etapa>.md` (Id · Before · After · Why).
4. Entre etapas, confira o relatório contra o arquivo de decisões antes de lançar a próxima (um agente pode "corrigir" uma decisão do time a partir de um arquivo velho). Mande status por etapa.
5. Fim: Opus lê a série inteira e confere a rastreabilidade R# → elemento da solução → ADR → HLD → teste; README com "What changed in revision N"; permalinks; privacy scan; build; publicação com a palavra do usuário.
6. Relatório ao usuário: decisões que mudaram (uma linha cada, com motivo), perguntas novas com dono, o que ficou de fora.
