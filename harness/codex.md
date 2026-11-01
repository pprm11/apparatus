### Adaptador: Codex

- Início de sessão: leia o `MEMORY.md` do projeto atual e abra só memórias relevantes, conforme
  `context-recall`; para gravar, use `context-ingest`.
- Telinha: use o plugin `visualize` se ele estiver disponível na sessão; sem ele, tabela em markdown.
- Níveis de modelo (A5, B11, B20): Luna para trabalho mecânico e barato; Terra para implementação e
  revisão técnica; Claude para uma segunda opinião quando útil. Use os nomes que a ferramenta oferecer
  na sessão e informe modelo e esforço ao delegar: low no mecânico, medium para ler/escrever, high ou
  xhigh no julgamento final. Se o modelo escolhido estiver indisponível, diga o substituto e o motivo.
- Subagentes (skill `orquestrar-cruzado`): prefira a ferramenta nativa quando ela deixar escolher o modelo
  (`gpt-6-luna`, `gpt-6.1-terra`; confirme na sessão); brief autossuficiente (`fork_turns="none"` se
  preciso); cada escritor na sua worktree. `create_thread` só com pedido de sessão nova (assunto novo na
  orquestradora conta). Sem mensagem entre sessões, a filha avisa o pai com `decisions.py add "Aviso ao
  orquestrador: ..."`. Filhos no Claude: `python -I ~/Codes/superego/tools/delegate.py run --brief-file <f>
  --cwd <repo> --to claude --tier mid [--write] [--background]`; `--to codex --tier` usa o modelo
  configurado, confira o comando antes de dizer qual foi.
- Caixa de decisões (B22): `python -I ~/Codes/superego/tools/decisions.py list | add | resolve | apply`.
  A página no claude.ai é republicada pela tarefa diária do Claude; o Codex só mexe nos dados.
- Sem hooks: nada bloqueia segredo no prompt (B15 é só o aviso), nada barra `find /` (vale a regra pelo
  texto) e nada refaz o índice sozinho (`context-ingest` manda rodar o rebuild).
- Skills: as portáveis estão em `~/.codex/skills` como links para `~/.claude/skills`. `telinhas`,
  `executar-ondas` e `orquestrar-sonnet-haiku` são só do Claude.
- Jobs: não rode `weekly.sh` nem registre tarefa agendada. Não edite as cópias nos repos de camada, que o
  sync sobrescreve; edite em `~/.claude`, e o sync regenera o `~/.codex/AGENTS.md`.
