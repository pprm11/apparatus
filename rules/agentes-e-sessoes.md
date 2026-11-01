# Agentes e sessões

Um condutor por execução de ondas ou workflow; o orquestrador delega, não edita o delegado; um escritor por
arquivo; gate otimista local e CI como gate real; achado recorrente vira lint ou teste. Para coordenação e
arquivamento, siga a skill `orquestrar-cruzado`.

## Push após aprovação

Com aprovação válida, ninguém dá push na PR, salvo rejeição da fila de merge, conflito ou CI quebrado; o
resto vai em PR empilhada. Essas exceções dependem da autorização de publicação vigente e não concedem
permissão nova. Commit local segue as regras já vigentes.
