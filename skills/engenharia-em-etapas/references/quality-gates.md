# Três portões por etapa: bem escrito, correto, otimizado

Uma etapa só fecha quando passa nos três. São perguntas diferentes, com revisores diferentes, e uma não cobre a outra: o texto pode estar impecável e o design errado; o design pode estar certo e caro ou complicado demais. Pedido do usuário em 28/10/2026: "Não basta tá bem escrito, a solução tem que tá correta e bem escrita", depois "bem escrito, correto e otimizado".

| Portão | Pergunta | Revisor | Evidência que conta |
|---|---|---|---|
| **Bem escrito** | Um leitor frio entende, confere e decide sem perguntar? | Sonnet com `technical-doc-readability` + leitor frio (outro agente, sem contexto) | Resposta do leitor frio às perguntas do gabarito; `preserve.py`; rastreabilidade; fonte em todo número |
| **Correto** | Faz o que precisa, inclusive quando algo dá errado? | Opus adversarial por área + segunda opinião de outro modelo (Codex) | Contraexemplo, script que explora interleavings, recálculo, POC com controle negativo, documentação oficial com URL e data |
| **Otimizado** | É o jeito mais simples e barato que dá as mesmas garantias, inclusive trocando a tecnologia ou tirando a peça? | Opus "o que dá para tirar, juntar ou baratear" + script de medição | Conta antes e depois (custo, chamadas por mensagem, latência por salto, nós, testes), alternativa mais simples testada e por que perde |

Regra de passagem, igual nos três: zero achado *blocking*; cada *major* corrigido ou aceito pelo dono como limite L# com motivo; *minor* vira item no README. Correção mexeu numa etapa: roda de novo o portão daquela área e a cascata das seguintes. Se o número de blocking não cair por 4 rodadas, pare e mostre os números ao usuário.

Formato de achado (os três portões): Id · Portão · Severidade · Onde (arquivo, seção, ID) · O que · Evidência · Menor correção. Conflito com decisão do time vira pergunta para os donos, nunca correção. Cada revisor fecha com "Checked and passes": o que verificou e passou, para saber o que foi coberto.

## Critérios por etapa

### 1 Domínio do problema
- **Bem escrito**: "In one minute" com resposta e pedido; glossário com nome de mercado e um termo por conceito; todo R# em EARS com BCP 14; cada Q# com dono e efeito de cada resposta; leitor frio responde "o que precisa ser verdade e como saber".
- **Correto**: requisitos consistentes entre si e com as decisões do time; juntos atingem os objetivos (contraexemplo de negócio não quebra nenhum); cada AC falharia se o requisito quebrasse; critérios de estágio com poder estatístico no volume dito (efeito mínimo detectável com alpha 0,05 e poder 0,8, calculado em script); suposições que o as-is pode derrubar estão marcadas.
- **Otimizado**: nenhum requisito sem objetivo ou decisão por trás (gold plating sai ou vira non-goal); escopo cortado por valor; cada AC é o sinal observável mais barato que prova o requisito; perguntas ordenadas pelo quanto destravam.

### 2 As-is
- **Bem escrito**: palavras de estado com um sentido só; toda afirmação com tag; "o que isso significa para o design" em restrições AS#; leitor frio sabe onde cada peça roda.
- **Correto**: cada fato reproduz pela tag (arquivo no commit, comando de leitura); NOT VERIFIED só onde nenhuma checagem chegou, com o comando que verificaria; nenhuma suposição da etapa 1 contradita sem pergunta; recheck não mudou os fatos principais.
- **Otimizado**: profundidade de checagem proporcional ao quanto o fato muda decisão (fato que não muda nada não ganha checagem cara); a checagem mais barata e só de leitura; a etapa traz o resumo e aponta para o relatório completo em vez de repetir.

### 3 Estudo de mercado
- **Bem escrito**: cada prática com fonte, data e rótulo; tabela adotado / adaptado / rejeitado com "onde na série" e "por quê".
- **Correto**: a fonte diz o que a série afirma (reaberta); rótulo certo (página lida inteira ou só busca); número usado do jeito que a fonte mede.
- **Otimizado**: reusa o que o mercado e o time já têm antes de construir (cada "construir" diz por que nada pronto serve); só entra benchmark que alguma decisão usa; esforço de pesquisa proporcional ao risco da decisão.

### 4 Domínio da solução
- **Bem escrito**: contextos, agregados, invariantes, comandos e políticas com IDs e trace para R# e AS#; quem pode emitir cada comando.
- **Correto**: toda invariante vale sob concorrência, falha, reentrega e relógio fora de sincronia (tabela invariante × evento, script de interleavings); o modelo cobre todo R#; nenhuma política contradiz outra.
- **Otimizado**: cada peça com estado é questionada: o requisito precisa mesmo de estado guardado, ou um cálculo determinístico (hash, regra) dá a mesma garantia? Onde o estado pode morar com menos custo (num sistema que já existe, no próprio evento)? Depois, o menor modelo que cumpre todos os R# (menos contextos, agregados, comandos e estados); nenhum elemento órfão; o mecanismo de consistência mais simples que basta (escrita condicional antes de transação, transação antes de lock); posicionamento com menos saltos e menos mudança de dono.

### 5 HLA
- **Bem escrito**: ADRs "We will" com a alternativa mais forte e consequências negativas; diagrama do que passa e do que não passa; custo 1-3-1 com fonte de preço e de volume.
- **Correto**: limites e timeouts da plataforma cabem em toda a cadeia (documentação oficial); alarmes disparam na falha que dizem pegar; corte e bypass sem perda nem duplicação; custo recalculado em script bate com a tabela; ADRs não se contradizem.
- **Otimizado**: cada tecnologia comparada com pelo menos uma alternativa real e com a opção de não ter a peça (outro banco, outro runtime, um serviço que o time já opera, nenhum componente novo), com custo, latência e operação medidos; custo mínimo hoje e no alvo, com o ponto de cruzamento e o que mudaria a escolha; menos peças para operar (serviço gerenciado antes de servidor, componente que o time já opera antes de novo); latência por salto dentro do orçamento com folga medida; decisões reversíveis onde der.

### 6 HLD
- **Bem escrito**: toda rota com exemplo completo; itens com chaves e campos; algoritmos com condições escritas (ALG#); modos de falha com detecção e recuperação; tabela de cobertura.
- **Correto**: condições de escrita certas (cada ConditionExpression revisada contra a invariante); POCs com controle negativo provam o que dizem; tratamento de erro e reentrega idempotente; nada de dado pessoal em log, trace ou chave.
- **Otimizado**: leituras e escritas no banco por mensagem contadas por caminho (e o mínimo possível); chamadas de rede no caminho síncrono só as necessárias; cold start e tamanho do pacote medidos; volume de log e de trace com custo; configuração com o menor número de chaves.

### 7 Plano de testes
- **Bem escrito**: cada caso Given / When / Then com o ID que prova; matriz de cobertura; ambientes, dados e bloqueios com dono; critérios de entrada e saída por ambiente e estágio.
- **Correto**: cada teste falharia se o comportamento estivesse errado (controle negativo executado ou mutação manual); cobre todo AC, QS, invariante, modo de falha, alarme e critério de estágio; os ambientes e dados existem ou o bloqueio está nomeado; nenhum teste toca API real de produção.
- **Otimizado**: cada risco testado no nível mais barato que o pega (pirâmide: unitário e propriedade antes de integração, integração antes de PRD); sem caso duplicado; tempo da suíte medido; amostra de cada estágio no mínimo que dá a decisão; o que roda em CI a cada PR separado do que roda antes de cada estágio.

## Como rodar com vários agentes

- Bem escrito: um Sonnet aplica `technical-doc-readability` e `preserve.py`; outro agente, sem contexto, responde o gabarito da etapa (perguntas que um leitor frio precisa responder) só com o documento.
- Correto: um Opus por área com `correctness-brief.md` (algoritmos e concorrência; arquitetura, limites e custo; requisitos contra o as-is; evidências e POCs) e um Codex com o mesmo escopo, sem ver os outros achados.
- Otimizado: um Opus com a pergunta "o que dá para tirar, juntar, trocar de tecnologia ou baratear mantendo cada R#, AC e invariante", começando pela pergunta mais cara de errar: esta peça precisa existir?, com script de medição (custo por linha, chamadas e unidades de capacidade do DynamoDB por caminho, saltos e latência, tempo da suíte de testes).
- Os três rodam em paralelo; os achados se juntam numa tabela; correções por etapa; nova rodada só nas áreas mexidas.
