# Twitter Data Pipeline — Avaliação de APIs & Estratégia

> **Data**: 05/Jun/2026 | **Autor**: Hermes + Jones | **Status**: MVP em construção

---

## 1. Objetivo

Pipeline leve e barato para:
- **Trending Topics**: Coletar trends do X (global, Brasil, categorias)
- **Monitoramento de @users**: Timeline diária de usuários específicos

Sem API oficial (cara: Basic $100/mês, Pro ~$5k/mês).

---

## 2. Descoberta Crítica (05/Jun/2026)

### Todas as libs gratuitas baseadas em JS parsing estão quebradas

O X mudou o mecanismo de `X-Client-Transaction-Id` (~Abril-Maio/2026) e **quebrou simultaneamente** twikit, tweety-ns, TweeterPy.

| Lib | Stars | Status | Causa |
|-----|-------|--------|-------|
| twikit 2.3.3 | 4.5k | ❌ Quebrada | `Couldn't get KEY_BYTE indices` |
| tweety-ns | 659 | ❌ Quebrada | Mesmo erro |
| TweeterPy | 325 | ⚠️ Parcial | `get_user_id()` funciona, resto não |
| twscrape 0.18.1 | 2.4k | ✅ Funciona | Requer contas X configuradas |
| twitter-scraper-selenium | 340 | ❌ Quebrada | ImportError interno |

**Lição**: GitHub stars ≠ funciona hoje. Validação prática diária é obrigatória.

---

## 3. Stack Escolhida (3 Camadas)

```
┌─────────────────────────────────────────────────────────┐
│ CAMADA 1 — GRATUITO (MVP)                               │
│                                                         │
│ Agent-Reach (github.com/Panniantong/Agent-Reach)        │
│ • 21k ★ — atualizado Mai/2026                          │
│ • CLI Python, zero API key, MCP nativo                  │
│ • Lê Twitter, Reddit, YouTube, GitHub, Bilibili         │
│ • Instalação: 1 comando via Agent                       │
│                                                         │
│ twscrape (github.com/vladkens/twscrape)                 │
│ • 2.4k ★ — atualizado Mai/2026                         │
│ • Async + pool multi-conta com rotação automática       │
│ • Requer 3 contas X descartáveis (em criação)           │
├─────────────────────────────────────────────────────────┤
│ CAMADA 2 — PAGO BARATO (fallback)                       │
│                                                         │
│ twitterapi.io                                           │
│ • $0.15/1K tweets | 1 USD = 100k créditos               │
│ • Endpoints: /twitter/trends, /twitter/user/*, search   │
│ • Trustpilot 4.6★ | Suporte 24/7 via Telegram           │
│ • Custo estimado: ~$1.50/mês no nosso volume            │
│ • $10 recarga = ~6 meses de uso                         │
│ • $0.10 crédito grátis inicial (sem cartão)             │
├─────────────────────────────────────────────────────────┤
│ CAMADA 3 — PROTEÇÃO (proxy)                             │
│                                                         │
│ Decodo (decodo.com)                                     │
│ • Residential proxy desde $2/GB                         │
│ • 115M+ IPs, 195 países, rotating/sticky                │
│ • Só ativar se tomar ban nas contas                     │
└─────────────────────────────────────────────────────────┘
```

---

## 4. Serviços Avaliados e Descartados

| Serviço | Motivo |
|---------|--------|
| **tweepy** (11k★) | API oficial — Basic $100/mês |
| **Ayrshare** | API de POSTAGEM, não leitura de dados públicos |
| **Zernio** | API de POSTAGEM, mesmo caso |
| **Unipile** | API de MENSAGENS/DM, não scraping |
| **SociaVault** | Genérico multi-plataforma, $29/6K créditos, não Twitter-especializado |
| **Zylalabs** | Cloudflare bloqueou auditoria — risco não verificado |
| **fast-twitter-api** | Depende de twitterapi.io (já incluso na camada 2) |
| **bisguzar/twitter-scraper** (4k★) | Abandonado desde Out/2023 |
| **BANKA2017/twitter-monitor** | Purge de código Mar/2026 — instável |
| **trevorhobenshield/twitter-api-client** (1.9k★) | Sem update desde Mai/2024, 80 issues abertas |

---

## 5. KPIs de Validação (Framework)

### Tier 1 — Funcionalidade (diário)
- KPI-1: `get_trends('trending')` → ≥1 trend
- KPI-2: `get_trends` por categoria (news, sports, entertainment)
- KPI-3: `get_place_trends(WOEID)` → trends SP (455827) + NY (2459115)
- KPI-4: `get_user_by_screen_name(@user)` → retorna User
- KPI-5: `get_user_tweets(@user)` → ≥1 tweet
- KPI-6: `search_tweet(query)` → retorna resultados

### Tier 2 — Qualidade
- KPI-7: Frescor — delay X.com → scraper
- KPI-8: Completude — % tweets capturados vs perfil real
- KPI-9: Riqueza — campos: texto, likes, RTs, views, data

### Tier 3 — Robustez
- KPI-10: Success rate — % chamadas OK em 100 tentativas
- KPI-11: Latência p50/p95/p99 (ms)
- KPI-12: Rate limit — chamadas até bloqueio
- KPI-13: Tempo recuperação pós-erro

### Tier 4 — Operacional
- KPI-14: Tempo até 1ª chamada funcional
- KPI-15: Dias desde último commit do repo
- KPI-16: Issues abertas / velocidade resolução
- KPI-17: Custo diário/mensal $

---

## 6. Referências

| Recurso | URL |
|---------|-----|
| Agent-Reach | https://github.com/Panniantong/Agent-Reach |
| twscrape | https://github.com/vladkens/twscrape |
| twitterapi.io | https://twitterapi.io |
| twitterapi.io Docs | https://docs.twitterapi.io |
| twitterapi.io Pricing | https://twitterapi.io/pricing |
| Decodo Proxy | https://decodo.com |
| GitHub Topic: twitter-api | https://github.com/topics/twitter-api |
| Script Benchmark | `/tmp/twitter_benchmark.py` (local) |
| Resultados JSON | `/tmp/twitter_benchmark_results.json` (local) |

---

## 7. Próximos Passos

- [ ] Criar 3 contas X descartáveis (Jones)
- [ ] Criar conta gratuita twitterapi.io, testar `/twitter/trends`
- [ ] MVP: integrar Agent-Reach + twscrape → cron diário
- [ ] Definir lista inicial de @users para monitorar
- [ ] Alerta Telegram se KPI-1 falhar
- [ ] Avaliar Decodo apenas se contas tomarem ban

---

## 8. Histórico de Decisões

| Data | Decisão | Motivo |
|------|---------|--------|
| 05/Jun/2026 | twikit descartado | Quebrado — X-Client-Transaction-Id |
| 05/Jun/2026 | API oficial descartada | Custo proibitivo ($100-$5k/mês) |
| 05/Jun/2026 | Agent-Reach adicionado | 21k★ ativo, grátis, resolve Twitter |
| 05/Jun/2026 | twitterapi.io como fallback | $1.50/mês, confiável, trending+users |
| 05/Jun/2026 | Estratégia 3 camadas | Gratuito → Pago barato → Proxy |

---

*Documento mantido por Hermes Agent. Atualizar a cada mudança de stack ou descoberta.*
