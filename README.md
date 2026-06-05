# Twitter Data Pipeline 🐦

Pipeline leve e de baixo custo para coleta de **Trending Topics** e **Monitoramento de @users** no X/Twitter.

## Stack

| Camada | Tecnologia | Custo |
|--------|-----------|-------|
| 1 — Gratuito (MVP) | [Agent-Reach](https://github.com/Panniantong/Agent-Reach) + [twscrape](https://github.com/vladkens/twscrape) | $0 |
| 2 — Fallback pago | [twitterapi.io](https://twitterapi.io) | ~$1.50/mês |
| 3 — Proxy | [Decodo](https://decodo.com) | ~$2/GB |

## Documentação

- [Avaliação completa de APIs](EVALUATION.md) — todas as libs testadas, KPIs, benchmark
- [Script de benchmark](benchmark.py) — teste prático twikit vs twscrape

## Status

**Junho 2026**: twikit (4.5k★) quebrado por mudança no X. twscrape funcional com contas. twitterapi.io validado como fallback confiável a $1.50/mês.
