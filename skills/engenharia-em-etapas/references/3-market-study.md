# Etapa 3: estudo de mercado (prior art e benchmarks)

Leitor: revisor que quer saber se a série reinventa algo que o mercado já resolveu. É uma etapa própria, com a análise completa; as etapas 4, 5 e 6 trazem só um resumo de 3 linhas com link para cá.

## Esqueleto

```
# Market study: prior art and benchmarks
Series: ...
## In one minute            verdict, the ask, what the market covers, what it does not, the numbers that drive decisions
## Method                   how sources were read; label each claim: independent measurement, vendor claim, search-only
## Prior art and market practices
### <family 1> (e.g. experimentation platforms: Statsig, LaunchDarkly, GrowthBook, Eppo)
### <family 2> (e.g. progressive delivery: Argo Rollouts, Flagger, Istio/Envoy, AppConfig)
### <family 3> (e.g. agent platforms, the channel provider's own features)
## Adopted, adapted or rejected   table: practice · source · verdict · where in the series · why
## Public benchmarks        table: number · what it measures · source with date · label · where the series uses it
## Gaps                     what has no public number and how HML will measure it
## Open questions · ## Next steps
```

## Como fazer

1. Parta dos requisitos R# e das restrições AS#: para cada um, quem no mercado resolve isso e como (sticky bucketing, exposure log, kill switch, stage ladder, holdout).
2. Pesquisa web em rodadas (standard primeiro; extended só para número difícil ou recente). Toda fonte com título, editor, URL e data de acesso. Fornecedor falando de si, em página lida inteira, é "vendor claim". Página lida só por resumo ou snippet é "search-only", seja quem for o editor. WebFetch da página conta como página lida quando a afirmação vem do texto buscado; só o resultado da busca é "search-only".
3. Benchmark só entra se for usado numa decisão (cold start, latência, custo por milhão, política de reenvio do provedor). Número sem uso sai.
4. Nomes de mercado alimentam o glossário da etapa 1 (se mudar termo, é cascata).

## Pronto quando

Cada prática citada nas etapas seguintes tem uma linha na tabela adotado/adaptado/rejeitado, e cada número de benchmark usado numa decisão tem fonte, data e rótulo.
