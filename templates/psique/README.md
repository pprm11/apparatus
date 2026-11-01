# psique de {{name}}

Repositório meta do contexto de agente de {{name}} (`{{github}}`), criado em {{date}} por
`tools/onboard.py init` do superego. Ele não guarda contexto próprio: o `manifest.json` lista as camadas, na
ordem em que carregam.

| Nível | O que é | Quem altera |
|---|---|---|
| superego | regras gerais e ferramentas (repositório compartilhado, versão fixada em `ref`) | só o dono do superego |
| collective | o que o time compartilha (somente leitura aqui) | PR, com `onboard.py contribute` |
| ego | a empresa ou o projeto (somente leitura aqui) | PR, com `onboard.py contribute` |
| id | você: preferências, PDI, memórias pessoais (privado) | você, direto |

Memórias e skills sem `level:` no frontmatter vão para o `id` (`default_level`), nunca para uma camada compartilhada.

## Comandos

    python -I ~/Codes/superego/tools/onboard.py update --push    # o job horário faz isso
    python -I ~/Codes/superego/tools/onboard.py update --upgrade # sobe a versão fixada do superego
    python -I ~/Codes/superego/tools/onboard.py doctor
    python -I ~/Codes/superego/tools/onboard.py uninstall

Este repositório é privado e fica na sua conta. Não coloque nele nada de outra empresa ou pessoa.
