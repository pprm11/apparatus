# Mapa do contexto do agente (onde cada coisa mora)

Vale para o Claude Code e para o Codex. A fonte da verdade é `~/.claude`; o Codex lê o mesmo conteúdo pelo
`~/.codex/AGENTS.md`, gerado por `render_harness.py` (não edite o gerado).

Cada camada (ver o glossário do superego) é um repo em `~/Codes/`; o meta `psique` gera o `CLAUDE.md` raiz.
Toda memória e toda skill leva `level:` no frontmatter; sem o campo, vale ego. Cada camada tem um glossário
(campo `glossary` do `layer.json`, mesmo formato: versão, colisões, termos padrão, como interpretar pedidos);
o sync roda `tools/lint_glossary.py` e barra colisão não declarada.

Sempre carregado: `~/.claude/CLAUDE.md` (gerado pelo psique: globais de cada camada, na ordem, mais o adaptador
`harness/<harness>.md`) e `~/.claude/rules/*.md`. Só mude esses arquivos com o sim do usuário.

Memória, separada por projeto em `~/.claude/projects/<chave>/memory/`, com um `MEMORY.md` de índice. Só o
índice do projeto atual é carregado. Quando o assunto for de outro projeto, leia o `MEMORY.md` dele.

Para buscar além do índice atual, use `context-recall`; para gravar memória e reconstruir o índice,
use `context-ingest`.

Procedimentos: `~/.claude/skills/` (as portáveis também em `~/.codex/skills/`, como links). Scripts:
`~/.claude/scripts/`. Skill, hook ou script pessoal fica aqui, nunca em branch ou PR de repo do time: repo do
time só recebe mudança do escopo da task.
