#!/usr/bin/env python3
"""
Twitter Account Warmup & Human Behavior Simulator
==================================================
Faz a conta parecer "normal" antes de usar para scraping pesado.

Estratégia anti-detecção:
1. Scrollar timeline (simula usuário real)
2. Delay aleatório entre ações (1-5 min)
3. Só leitura — nunca like, RT, follow
4. Volume baixo: 10-20 ações/dia na 1ª semana
5. User-Agent mobile realista
"""

import asyncio
import random
import time
from datetime import datetime

from twscrape import API


# ── Comportamento humano simulado ──

HUMAN_DELAYS = {
    "scroll": (3, 8),       # segundos entre "scrolls"
    "read_tweet": (5, 15),  # tempo "lendo" um tweet
    "visit_profile": (8, 20),  # tempo "olhando" um perfil
    "between_sessions": (300, 900),  # 5-15min entre sessões
}

TOPIC_POOL = [
    "python programming",
    "javascript",
    "AI",
    "machine learning",
    "open source",
    "tech news",
    "data science",
    "linux",
]

PROFILE_POOL = [
    "github",
    "vercel",
    "openai",
    "deepseek_ai",
    "stackblitz",
    "v0",
    "cursor_ai",
    "replit",
]


async def human_delay(action: str):
    """Delay aleatório simulando tempo humano"""
    lo, hi = HUMAN_DELAYS.get(action, (1, 3))
    await asyncio.sleep(random.uniform(lo, hi))


async def warmup_session(api: API, account_name: str, intensity: str = "light"):
    """
    Simula uma sessão de navegação humana.
    
    intensity: "light" (5 ações), "medium" (10 ações), "heavy" (15 ações)
    """
    actions = {"light": 5, "medium": 10, "heavy": 15}[intensity]
    
    print(f"\n🔄 Warmup session for @{account_name} ({intensity}: {actions} ações)")
    
    # 1. Abrir timeline (como quem abre o app)
    print("  📱 Abrindo timeline...")
    try:
        await human_delay("scroll")
        # Não precisamos fazer nada — só o delay simula
    except Exception as e:
        print(f"  ⚠️ Timeline skip: {e}")
    
    # 2. Scrollar + ler alguns tweets aleatórios
    topics = random.sample(TOPIC_POOL, min(3, actions // 2))
    for topic in topics:
        print(f"  🔍 Buscando: '{topic}'...")
        try:
            count = 0
            async for tweet in api.search(topic, limit=3):
                count += 1
                await human_delay("read_tweet")
            print(f"    → {count} tweets lidos")
        except Exception as e:
            print(f"    ⚠️ Erro (esperado em conta nova): {type(e).__name__}")
        await human_delay("scroll")
    
    # 3. Visitar perfis variados (não os monitorados!)
    profiles = random.sample(PROFILE_POOL, min(3, actions // 3))
    for profile in profiles:
        print(f"  👤 Visitando @{profile}...")
        try:
            user = await api.user_by_login(profile)
            if user:
                print(f"    → {user.followersCount:,} followers")
            await human_delay("visit_profile")
        except Exception as e:
            print(f"    ⚠️ Erro: {type(e).__name__}")
    
    # 4. Trending (olhar o que está acontecendo)
    print("  📈 Olhando trending...")
    try:
        async for trend in api.trends("trending", limit=5):
            await asyncio.sleep(0.5)  # scroll rápido entre trends
        print("    → ✓")
    except Exception as e:
        print(f"    ⚠️ Erro: {type(e).__name__}")
    
    print(f"  ✅ Sessão concluída")


async def daily_warmup(api: API, account_name: str, day: int):
    """
    Plano de warmup de 7 dias:
    Dia 1-2: 1 sessão light
    Dia 3-4: 2 sessões light  
    Dia 5-6: 1 medium + 1 light
    Dia 7+:  2 medium
    """
    if day <= 2:
        await warmup_session(api, account_name, "light")
    elif day <= 4:
        await warmup_session(api, account_name, "light")
        await human_delay("between_sessions")
        await warmup_session(api, account_name, "light")
    elif day <= 6:
        await warmup_session(api, account_name, "medium")
        await human_delay("between_sessions")
        await warmup_session(api, account_name, "light")
    else:
        await warmup_session(api, account_name, "medium")
        await human_delay("between_sessions")
        await warmup_session(api, account_name, "medium")


# ── MAIN ──

async def main():
    import sys
    
    account = sys.argv[1] if len(sys.argv) > 1 else "hermes_santosBR"
    day = int(sys.argv[2]) if len(sys.argv) > 2 else 1
    
    api = API("accounts.db")
    info = await api.pool.accounts_info()
    
    active = [a for a in info if a.get("active")]
    if not active:
        print("❌ Nenhuma conta ativa. Execute setup_twscrape.py primeiro.")
        return
    
    print(f"📅 Dia {day} de warmup")
    await daily_warmup(api, account, day)
    
    print(f"\n📊 Status da conta:")
    for a in await api.pool.accounts_info():
        print(f"  @{a['username']}: active={a['active']}, locked_until={a.get('locked_until', 'none')}")


if __name__ == "__main__":
    asyncio.run(main())
