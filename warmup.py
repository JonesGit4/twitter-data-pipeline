#!/usr/bin/env python3
"""
Twitter Account Warmup v2 — Fully Automated with Day Tracking
==============================================================
Estratégia anti-ban de 7 dias com tracking automático de progresso.
Roda diariamente via cron, auto-incrementa o dia, nunca perde estado.

Princípios anti-detecção:
1. Progressive warmup: 5 ações/dia → 20 ações/dia em 7 dias
2. Human-like delays: 3-8s scroll, 5-15s leitura, 8-20s visita perfil
3. 2 sessões/dia separadas por 5-15min (ninguém faz tudo em 2min)
4. Read-only: NUNCA like, RT, follow, post
5. Perfis genéricos primeiro, alvos só depois do dia 5
6. Horário BR: 9h-22h BRT (via cron)
7. User-Agent mobile realista
8. Cookies frescos (importados do navegador)

Uso: python3 warmup.py
(O dia é lido/atualizado automaticamente do state file)
"""

import asyncio
import json
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from twscrape import API

# ── Config ──────────────────────────────────────────────────
SCRIPT_DIR = Path(__file__).parent
STATE_FILE = SCRIPT_DIR / "warmup_state.json"
DB_PATH = SCRIPT_DIR / "accounts.db"
LOG_FILE = SCRIPT_DIR / "warmup.log"

NOCODB_BASE = "phau7rzz1zwsr67"
NOCODB_TABLE = "mv7yhsifwybqcer"
NOCODB_TOKEN = "nc_pat_Gk9mhaSo8kBRRZbqDhMlilu295RzJXumzZYotk1z"
NOCODB_URL = "https://app.nocodb.com/api/v2"

HUMAN_DELAYS = {
    "scroll": (3, 8),
    "read_tweet": (5, 15),
    "visit_profile": (8, 20),
    "between_actions": (2, 5),
    "between_sessions": (300, 900),  # 5-15min
}

TOPIC_POOL_LIGHT = [
    "python programming", "javascript", "AI",
    "open source", "tech news", "linux",
]

TOPIC_POOL_FULL = TOPIC_POOL_LIGHT + [
    "machine learning", "data science", "cloud computing",
    "docker", "kubernetes", "react", "typescript",
    "devops", "api", "database",
]

PROFILE_POOL_NEUTRAL = [
    "github", "vercel", "openai", "deepseek_ai",
    "stackblitz", "v0", "cursor_ai", "replit",
    "netlify", "supabase", "linear", "notionhq",
]

PROFILE_POOL_TARGETS = [
    "FlavioBolsonaro", "elonmusk",
]

# ── State Management ────────────────────────────────────────

def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {
        "account": "hermes_santosBR",
        "current_day": 1,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "last_run": None,
        "total_sessions": 0,
        "total_actions": 0,
        "errors": 0,
        "locked": False,
    }

def save_state(state):
    state["last_run"] = datetime.now(timezone.utc).isoformat()
    STATE_FILE.write_text(json.dumps(state, indent=2, default=str))

def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")

# ── Human Behavior Simulation ───────────────────────────────

async def human_delay(action: str):
    lo, hi = HUMAN_DELAYS.get(action, (1, 3))
    await asyncio.sleep(random.uniform(lo, hi))


# ── NocoDB Follow Queue ─────────────────────────────────────

def get_follow_queue(account: str):
    """Busca handles pendentes na fila do NocoDB para esta conta scraper."""
    import urllib.request, json as _json
    
    url = (f"{NOCODB_URL}/tables/{NOCODB_TABLE}/records"
           f"?where=(Status,eq,Pendente)~and(Conta Scraper,eq,{account})"
           f"&limit=5&sort=Adicionado em")
    
    req = urllib.request.Request(url)
    req.add_header("xc-token", NOCODB_TOKEN)
    req.add_header("Accept", "application/json")
    
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        data = _json.loads(resp.read())
        return data.get("list", [])
    except Exception as e:
        log(f"  ⚠️ NocoDB fetch error: {e}")
        return []

def update_follow_status(record_id, status, account):
    """Atualiza status de um registro na fila."""
    import urllib.request, json as _json
    
    url = f"{NOCODB_URL}/tables/{NOCODB_TABLE}/records"
    body = _json.dumps({
        "Id": record_id,
        "Status": status,
        "Seguido em": datetime.now(timezone.utc).isoformat(),
    }).encode()
    
    req = urllib.request.Request(url, data=body, method="PATCH")
    req.add_header("xc-token", NOCODB_TOKEN)
    req.add_header("Content-Type", "application/json")
    
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception as e:
        log(f"  ⚠️ NocoDB update error: {e}")


async def follow_from_queue(api: API, account: str, max_follows: int = 2):
    """Segue contas da fila do NocoDB via Twitter GraphQL (twscrape é read-only)."""
    import aiohttp
    import urllib.request, json as _json
    
    queue = get_follow_queue(account)
    
    if not queue:
        log("  📋 Fila de follows vazia")
        return 0
    
    # Get cookies for GraphQL auth
    try:
        acc_info = await api.pool.accounts_info()
        cookies_str = None
        for a in acc_info:
            if a.get("username") == account:
                cookies_str = a.get("cookies", "")
                break
        if not cookies_str or cookies_str == "{}":
            log("  ⚠️ Sem cookies para autenticação GraphQL")
            return 0
        # Parse cookies from twscrape format
        cookies_dict = {}
        for pair in cookies_str.split("; "):
            if "=" in pair:
                k, v = pair.split("=", 1)
                cookies_dict[k] = v
    except Exception as e:
        log(f"  ⚠️ Erro ao carregar cookies: {e}")
        return 0
    
    to_follow = queue[:max_follows]
    followed = 0
    
    async with aiohttp.ClientSession(cookies=cookies_dict) as session:
        for item in to_follow:
            handle = item.get("Handle", "").strip().lstrip("@")
            record_id = item.get("Id")
            
            if not handle:
                continue
            
            log(f"  ➕ Seguindo @{handle} (da fila NocoDB)...")
            try:
                # Step 1: Get user ID
                user_data = await api.user_by_login(handle)
                if not user_data:
                    update_follow_status(record_id, "Erro", account)
                    log(f"    → ❌ Usuário @{handle} não encontrado")
                    continue
                user_id = user_data.id
                
                # Step 2: Follow via GraphQL
                # Operation ID for Follow mutation (stable)
                headers = {
                    "authorization": "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA",
                    "content-type": "application/json",
                    "x-twitter-active-user": "yes",
                    "x-twitter-auth-type": "OAuth2Session",
                    "x-csrf-token": cookies_dict.get("ct0", ""),
                }
                
                follow_url = "https://x.com/i/api/1.1/friendships/create.json"
                payload = {
                    "user_id": str(user_id),
                    "include_blocked_by": False,
                    "include_blocking": False,
                    "include_can_dm": False,
                    "include_followed_by": False,
                    "include_want_retweets": True,
                    "skip_status": True,
                }
                
                async with session.post(follow_url, json=payload, headers=headers) as resp:
                    if resp.status == 200:
                        update_follow_status(record_id, "Seguindo", account)
                        log(f"    → ✅ @{handle} seguido")
                        followed += 1
                    elif resp.status == 403:
                        update_follow_status(record_id, "Erro", account)
                        log(f"    → ❌ 403 Forbidden @{handle} (conta pode estar limitada)")
                    else:
                        text = await resp.text()
                        update_follow_status(record_id, "Erro", account)
                        log(f"    → ❌ HTTP {resp.status} @{handle}: {text[:100]}")
                
                await human_delay("between_actions")
                
            except Exception as e:
                log(f"    → ❌ Erro: {type(e).__name__}: {e}")
                update_follow_status(record_id, "Erro", account)
    
    return followed

async def scroll_timeline(api: API):
    """Simula abrir o app e scrollar a timeline — ação mais comum de humano.
    Usa search genérico como proxy (twscrape v0.18 não tem api.timeline)."""
    log("  📱 Scrollando timeline (For You)...")
    # Busca genérica simula o feed "For You" — tópicos variados
    generic_queries = ["tech news", "today", "trending", "news", "update"]
    query = random.choice(generic_queries)
    try:
        count = 0
        async for tweet in api.search(query, limit=5):
            count += 1
            await human_delay("read_tweet")
        log(f"    → {count} tweets scrollados")
        return count
    except Exception as e:
        log(f"    ⚠️ Timeline: {type(e).__name__}")
        return 0

async def search_topics(api: API, day: int, intensity: str):
    """Busca tópicos variados — genéricos no início, específicos depois."""
    pool = TOPIC_POOL_FULL if day >= 4 else TOPIC_POOL_LIGHT
    n_topics = {"light": 2, "medium": 3, "heavy": 4}[intensity]
    topics = random.sample(pool, min(n_topics, len(pool)))
    
    total = 0
    for topic in topics:
        log(f"  🔍 Buscando: '{topic}'...")
        try:
            count = 0
            async for tweet in api.search(topic, limit=3):
                count += 1
                await human_delay("read_tweet")
            log(f"    → {count} tweets")
            total += count
        except Exception as e:
            log(f"    ⚠️ {type(e).__name__}")
        await human_delay("between_actions")
    return total

async def visit_profiles(api: API, day: int, intensity: str):
    """Visita perfis — neutros nos primeiros dias, alvos só do dia 5+."""
    pool = PROFILE_POOL_NEUTRAL.copy()
    if day >= 5:
        # Introduz 1 alvo por sessão a partir do dia 5
        pool = pool + PROFILE_POOL_TARGETS
    
    n_profiles = {"light": 1, "medium": 2, "heavy": 3}[intensity]
    profiles = random.sample(pool, min(n_profiles, len(pool)))
    
    for profile in profiles:
        log(f"  👤 Visitando @{profile}...")
        try:
            user = await api.user_by_login(profile)
            if user:
                log(f"    → {user.followersCount:,} seguidores, {user.statusesCount:,} tweets")
            await human_delay("visit_profile")
        except Exception as e:
            log(f"    ⚠️ {type(e).__name__}")
        await human_delay("between_actions")

async def check_trending(api: API):
    """Olha trending topics — comportamento de usuário casual."""
    log("  📈 Olhando trending...")
    try:
        async for trend in api.trends("trending", limit=5):
            await asyncio.sleep(0.5)
        log("    → ✓")
    except Exception as e:
        log(f"    ⚠️ {type(e).__name__}")

async def warmup_session(api: API, account: str, day: int, intensity: str, session_num: int):
    """
    Uma sessão de navegação simulando humano real.
    intensity: light (5 ações), medium (10), heavy (15)
    """
    actions_map = {"light": 5, "medium": 10, "heavy": 15}
    expected = actions_map[intensity]
    
    log(f"\n🔄 Sessão {session_num} — @{account} (dia {day}, {intensity}: ~{expected} ações)")
    
    actual = 0
    
    # 1. Abrir app = scroll timeline
    actual += await scroll_timeline(api)
    await human_delay("between_actions")
    
    # 2. Buscar tópicos
    actual += await search_topics(api, day, intensity)
    await human_delay("between_actions")
    
    # 3. Visitar perfis
    await visit_profiles(api, day, intensity)
    await human_delay("between_actions")
    
    # 4. Trending
    await check_trending(api)
    
    log(f"  ✅ Sessão {session_num} concluída (~{actual} interações)")
    return actual

# ── Daily Warmup Plan ───────────────────────────────────────

async def daily_warmup(api: API, account: str, day: int):
    """
    Plano progressivo de 7 dias:
    Dia 1-2: 1 sessão light (5 ações)
    Dia 3-4: 2 sessões light (10 ações)
    Dia 5-6: 1 medium + 1 light (20 ações)
    Dia 7+:  2 medium (25 ações)
    
    Follows da fila NocoDB: máx 2/dia, só a partir do dia 4.
    """
    if day <= 2:
        actions = await warmup_session(api, account, day, "light", 1)
    elif day <= 4:
        actions = await warmup_session(api, account, day, "light", 1)
        log("  ⏳ Aguardando entre sessões (5-15min)...")
        await human_delay("between_sessions")
        actions += await warmup_session(api, account, day, "light", 2)
    elif day <= 6:
        actions = await warmup_session(api, account, day, "medium", 1)
        log("  ⏳ Aguardando entre sessões (5-15min)...")
        await human_delay("between_sessions")
        actions += await warmup_session(api, account, day, "light", 2)
    else:
        actions = await warmup_session(api, account, day, "medium", 1)
        log("  ⏳ Aguardando entre sessões (5-15min)...")
        await human_delay("between_sessions")
        actions += await warmup_session(api, account, day, "medium", 2)
    
    # Follow queue: só a partir do dia 4, máx 2/dia
    if day >= 4:
        log("\n📋 Processando fila de follows...")
        await human_delay("between_sessions")
        followed = await follow_from_queue(api, account, max_follows=2)
        actions += followed
    
    return actions

# ── Main ────────────────────────────────────────────────────

async def main():
    state = load_state()
    account = state["account"]
    day = state["current_day"]
    
    log(f"{'='*50}")
    log(f"🔥 WARMUP DIA {day}/7 — @{account}")
    log(f"   Iniciado em: {state['started_at']}")
    log(f"   Último run:  {state['last_run'] or 'nunca'}")
    log(f"   Sessões: {state['total_sessions']} | Ações: {state['total_actions']} | Erros: {state['errors']}")
    
    # Check account status
    api = API(str(DB_PATH))
    info = await api.pool.accounts_info()
    
    active = [a for a in info if a.get("active")]
    if not active:
        log("❌ NENHUMA CONTA ATIVA! Execute setup_twscrape.py primeiro.")
        state["errors"] += 1
        save_state(state)
        sys.exit(1)
    
    for a in info:
        locked = a.get("locked_until")
        if locked:
            log(f"🔒 @{a['username']} BLOQUEADA até {locked}")
            state["locked"] = True
            save_state(state)
            sys.exit(0)
        else:
            log(f"✅ @{a['username']}: ativa, sem locks")
    
    # Run warmup
    try:
        actions = await daily_warmup(api, account, day)
        state["total_sessions"] += 1
        state["total_actions"] += actions
        
        # Avança para próximo dia
        if day < 7:
            state["current_day"] = day + 1
            log(f"\n📅 Dia {day} completo → próximo: dia {day + 1}")
        else:
            log(f"\n🎉 WARMUP COMPLETO! 7 dias concluídos. Conta pronta para scraping.")
            state["current_day"] = 8  # maintenance mode
        
    except Exception as e:
        log(f"❌ ERRO: {type(e).__name__}: {e}")
        state["errors"] += 1
        # NÃO avança o dia em caso de erro
    
    save_state(state)
    
    # Status final
    log(f"\n📊 Status pós-warmup:")
    for a in await api.pool.accounts_info():
        stats = json.loads(a.get("stats", "{}")) if isinstance(a.get("stats"), str) else (a.get("stats") or {})
        log(f"  @{a['username']}: active={a['active']}, locked={a.get('locked_until') or 'none'}")
        log(f"  stats: {json.dumps(stats)}")
    
    log(f"{'='*50}")


if __name__ == "__main__":
    asyncio.run(main())
