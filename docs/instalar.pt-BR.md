# Como instalar o contexto de agente (Claude Code e Codex)

Para quem entra num projeto que já usa este contexto em camadas e não é o dono do superego. Ao final você tem o
coletivo do projeto (a única camada compartilhada, somente leitura), o seu `ego` (a sua aplicação do coletivo, privada) e
o seu `id` privado na sua conta do GitHub, o
`~/.claude/CLAUDE.md` e o `~/.codex/AGENTS.md` prontos, e um job que atualiza tudo de hora em hora. Nada do dono
nem de outras empresas é instalado: o instalador confere isso antes e depois (`ci/privacy-terms.json`).

`<DONO>` abaixo é a conta do GitHub que te convidou. Os comandos prontos, com os nomes certos, vêm na mensagem do convite.

## Antes de começar

1. Aceite os convites do GitHub que chegaram por e-mail (superego e o coletivo do projeto). Sem o aceite o clone falha.
2. Tenha uma conta do GitHub sua. O instalador cria repositórios **privados** nela: `psique`, `id-context` e um `ego-NOME` para cada coletivo (as suas notas, preferências e contexto de trabalho naquela empresa). O ego é sempre seu: o instalador recusa o ego de outra pessoa.

## Passo a passo

1. **Instale git e gh e entre no GitHub.**

   Windows (PowerShell):

       winget install --id Git.Git -e
       winget install --id GitHub.cli -e
       gh auth login

   macOS:

       brew install git gh
       gh auth login

   Linux (Debian, Ubuntu):

       sudo apt-get install -y git
       # gh: https://github.com/cli/cli/blob/trunk/docs/install_linux.md
       gh auth login

   No `gh auth login` escolha GitHub.com, HTTPS e o navegador. Abra um terminal novo depois de instalar.

2. **Baixe o superego** (a parte compartilhada e somente leitura):

       gh repo clone <DONO>/superego ~/Codes/superego

   Hoje esse clone depende do convite para o superego. O caminho futuro é um espelho público do superego, sem histórico
   (`docs/public-mirror.md`): quando ele existir, este passo clona o espelho e só o coletivo continua por convite. Até
   lá vale o fluxo de convite descrito aqui.

3. **Rode o instalador** (ele acha o Python 3.10 ou mais novo e instala se faltar).

   Windows:

       & "$HOME\Codes\superego\install.ps1" init --layer collective:NOME=https://github.com/<DONO>/collective-NOME --root NOME=~/Codes/NOME

   macOS e Linux:

       ~/Codes/superego/install.sh init --layer collective:NOME=https://github.com/<DONO>/collective-NOME --root NOME=~/Codes/NOME

4. **Responda o que ele perguntar** (ou passe `--name` e `--github` para não ser perguntado):

   | Pergunta | O que responder |
   |---|---|
   | Seu nome | como você quer ser chamado nos arquivos do seu `id` |
   | Seu usuário no GitHub | o seu, não o do dono |

   **Passo do coletivo:** sem `--layer collective:...` ele lista os coletivos (`collective-*`) a que você tem acesso e
   pergunta quais anexar, em que pastas de projeto cada um vale (só ali, nunca misturado com outra empresa) ou se você
   quer pular (`--no-collective`) ou criar um novo, privado na sua conta, com o CI e a lista de termos de outras empresas
   (`--new-collective NOME --deny-company TERMO`). Com duas ou mais empresas, a home padrão não carrega nenhuma delas e
   cada uma ganha a sua em `~/.agent-homes/NOME`.

   `--layer collective:NOME=URL` anexa um coletivo (nome e URL); o seu `ego-NOME` é criado junto. `--root` diz em que pasta ficam os projetos daquela
   empresa. O instalador clona as camadas, cria o seu `psique`, o seu `id-context` e o seu `ego-NOME` a partir dos modelos, copia tudo
   para `~/.claude`, gera `CLAUDE.md` e `AGENTS.md`, agenda o job e roda o `doctor`.

5. **Cofre (opcional, pergunta no fim do init).** É o seu Bitwarden, a sua chave age e o backup cifrado dos seus segredos
   no seu `id`. Você faz sozinho: criar a conta em bitwarden.com (ou vault.bitwarden.eu, use `--bw-region eu`), definir uma
   senha mestra longa, ligar a verificação em duas etapas e guardar o código de recuperação. O instalador instala `bw` e
   `age`, pede `bw login` e a senha mestra no seu terminal, gera a chave age, guarda-a como nota `age-identity` no SEU cofre,
   confere por hash sem imprimir e salva só a chave pública. A chave privada não vai para o disco nem para a tela. Sucesso:
   a linha `cofre: chave age criada e verificada no cofre`. Para fazer depois: `onboard.py vault`.

6. **Confira.** O fim da saída deve dizer `0 failed`. Depois, entre nos agentes uma vez: `claude` (e `codex login`
   se usar o Codex). Para rodar o conferidor quando quiser:

       python -I ~/Codes/superego/tools/onboard.py doctor

No fim do init ele registra os jobs do seu sistema, roda uma sincronização e mostra o resultado. Os jobs são o `update`
(de hora em hora) e o `secrets` (só com o cofre). O `harvest` e o `weekly` do dono são scripts bash que escrevem dentro do checkout do superego, que para você é somente
leitura, por isso não existem na sua instalação. Gerenciar: `onboard.py jobs status|enable NOME|disable NOME|run NOME`.
O `doctor` mostra, por job, se está registrado, o último resultado e a próxima execução.

Rodar o passo 3 de novo é seguro: ele só completa o que falta. Se você já tinha um `~/.claude/CLAUDE.md` ou um
`~/.codex/AGENTS.md` seu, a cópia fica ao lado como `*.pre-psique` e volta no desinstalar.

## Dia a dia

- **Atualizar** (o job faz de hora em hora): `python -I ~/Codes/superego/tools/onboard.py update --push`. Puxa as camadas
  compartilhadas, recompõe os arquivos e faz o backup do seu `id` e dos seus `ego`.
- **Nova versão do superego** (ele fica fixado numa versão): `python -I ~/Codes/superego/tools/onboard.py update --upgrade`.
- **Memórias e skills suas** vão para o seu `id` privado (as que não têm `level:` no cabeçalho também). Para uma delas valer
  para o time, proponha pela PR abaixo.
- **Propor uma mudança numa camada compartilhada** (as camadas são somente leitura para você):

      python -I ~/Codes/superego/tools/onboard.py contribute start collective meu-termo
      # edite os arquivos na pasta indicada (rascunhos em proposed/), depois:
      python -I ~/Codes/superego/tools/onboard.py contribute submit <PASTA> -m "feat: adiciona o termo X"

  Com permissão de escrita ele envia a branch e abre a PR; sem ela tenta por fork (repositório privado de conta pessoal
  pode não permitir: nesse caso peça acesso de escrita ao dono). O CI do repositório barra nomes de outras empresas.

## Se der errado

| Sintoma | Causa | O que fazer |
|---|---|---|
| `sem acesso a <DONO>/...` | convite não aceito ou ainda não enviado | aceite o e-mail do GitHub ou peça o convite; rode o passo 3 de novo |
| `gh não está logado` | falta o `gh auth login` | rode-o e repita o passo 3 |
| `falta: git` ou `falta: gh` | ferramenta não instalada ou terminal antigo | passo 1 e abra um terminal novo |
| `VAZOU ... fonte` | uma camada compartilhada traz nome que não é seu | nada foi instalado; mande a linha ao dono da camada |
| `jobs: not registered` (aviso) | o agendador do seu sistema recusou | rode `python -I ~/Codes/superego/tools/scheduler.py install --manifest ~/Codes/psique/manifest.json --apply` |
| `claude` ou `codex` com aviso | não instalados | opcional: `npm install -g @anthropic-ai/claude-code` ou `@openai/codex` |
| macOS sem Python | Homebrew ausente | instale o Homebrew (brew.sh) e rode de novo |

## Desinstalar

    python -I ~/Codes/superego/tools/onboard.py uninstall --dry-run   # só mostra
    python -I ~/Codes/superego/tools/onboard.py uninstall

Remove os jobs, os arquivos copiados para `~/.claude`, o `AGENTS.md` gerado, os links de skills do Codex, os clones locais
das camadas, as homes por empresa, o estado e os logs do instalador e as pastas que ele criou; devolve os seus
`*.pre-psique`. Imprime cada item removido. Rodar de novo não faz nada. Clone seu (`psique`, `id-context`) com trabalho
que só existe local é mantido e avisado. Nunca apaga nada remoto (GitHub, Bitwarden). A chave age local só sai com
`--remove-age-key` e a sua confirmação. Apagar os seus repositórios no GitHub exige `--delete-remote-repos`,
`--confirm-remote-delete SEU_USUARIO` e digitar `APAGAR` (sem terminal: `--i-am-sure`). O helper de credenciais que o
`gh auth setup-git` pôs no git global fica, porque é do `gh`.

## Já tenho conta: trazer tudo para uma máquina nova

    python -I ~/Codes/superego/tools/onboard.py restore --github SEU_USUARIO

Clona o seu `psique` e todas as camadas que ele lista, abre o seu cofre, pega a nota `age-identity`, decifra o `sealed/` e o
backup de segredos sem sobrescrever arquivo existente, restaura, compõe, registra os jobs e roda o `doctor`. Use depois do
passo 1 e 2 acima (git, gh, superego). Sem o cofre aberto ele segue sem os segredos e diz o que faltou.

## Para quem convida

Antes de mandar o comando, na conta dona (troque `<USUARIO>`):

    gh api -X PUT repos/<DONO>/superego/collaborators/<USUARIO> -f permission=pull
    gh api -X PUT repos/<DONO>/collective-NOME/collaborators/<USUARIO> -f permission=pull
    
Use `permission=push` no coletivo em que a pessoa contribui por PR. Só o superego e o coletivo são compartilhados: nunca
convide para o `id`, o `psique` nem para o ego de ninguém (o ego é a aplicação privada de cada pessoa). Em conta pessoal o GitHub não impõe "só por PR" (sem proteção de branch em repositório privado): quem tem escrita
pode dar push direto; o CI roda e o `gitleaks` varre o histórico, mas não bloqueiam.
