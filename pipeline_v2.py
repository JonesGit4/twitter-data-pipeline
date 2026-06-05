#!/usr/bin/env python3
"""
Twitter Monitor — Pipeline v2
==============================
Tier VIP:   checa a cada 59min se postou algo novo
Tier Regular: checa 1x/dia às 23:55, só tweets se tweets_count mudou

Estratégia: /user/info (18 créditos) primeiro → só busca tweets (15/tweet) se count mudou
"""

import asyncio
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import httpx

# ═══════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════

API_KEY = os.getenv("TWITTERAPI_IO_KEY", "new1_6deba88d9fa94d4d9e01d6fca78fe035")
STATE_FILE = Path(os.path.expanduser("~/.hermes/data/twitter/monitor_state.json"))
OUTPUT_DIR = Path(os.path.expanduser("~/.hermes/data/twitter"))
RATE_LIMIT = 6.0  # segundos entre chamadas (free tier)

# Tiers
VIP_USERS = [
    "FlavioBolsonaro",
    "elonmusk",
]

REGULAR_USERS = [
    # Serão gerenciados via comandos +@ no grupo
]

WOEID_GLOBAL = 1
WOEID_BRAZIL = 455827
MAX_TWEETS_PER_USER = 5


# ═══════════════════════════════════════════════
# STATE MANAGEMENT
# ═══════════════════════════════════════════════

def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {
        "users": {
            "vip": VIP_USERS,
            "regular": REGULAR_USERS,
        },
        "snapshots": {},  # username → {tweets_count, followers, last_checked}
        "twitterapi_credits_remaining": "unknown",
    }


def save_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False))


# ═══════════════════════════════════════════════
# API CLIENT
# ═══════════════════════════════════════════════

class TwitterAPI:
    BASE = "https://api.twitterapi.io/twitter"
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = httpx.AsyncClient(
            headers={"X-API-Key": api_key},
            timeout=30.0,
        )
    
    async def get_user_info(self, username: str) -> dict:
        r = await self.client.get(f"{self.BASE}/user/info", params={"userName": username})
        r.raise_for_status()
        return r.json().get("data", r.json())
    
    async def get_user_tweets(self, username: str, count: int = 5) -> list[dict]:
        r = await self.client.get(f"{self.BASE}/user/last_tweets", params={"userName": username})
        r.raise_for_status()
        inner = r.json().get("data", {})
        return inner.get("tweets", [])[:count]
    
    async def get_trends(self, woeid: int = 1) -> list[dict]:
        r = await self.client.get(f"{self.BASE}/trends", params={"woeid": woeid})
        r.raise_for_status()
        raw = r.json().get("trends", [])
        return [t["trend"] for t in raw if "trend" in t]
    
    async def close(self):
        await self.client.aclose()


# ═══════════════════════════════════════════════
# CHECK LOGIC
# ═══════════════════════════════════════════════

async def check_user(api: TwitterAPI, username: str, state: dict, force: bool = False) -> Optional[dict]:
    """
    Verifica um @user. Só busca tweets se tweets_count mudou ou force=True.
    Retorna None se nada mudou, dict com dados se teve novidade.
    """
    prev = state["snapshots"].get(username, {})
    prev_count = prev.get("tweets_count", 0)
    
    # Sempre busca info (18 créditos)
    await asyncio.sleep(RATE_LIMIT)
    info = await api.get_user_info(username)
    
    current_count = info.get("statusesCount", 0)
    followers = info.get("followers", 0)
    
    # Atualiza snapshot
    state["snapshots"][username] = {
        "tweets_count": current_count,
        "followers": followers,
        "last_checked": datetime.now(timezone.utc).isoformat(),
    }
    
    has_new = current_count > prev_count
    
    if not force and not has_new:
        return None  # nada novo, economiza chamada de tweets
    
    # Busca tweets (15 créditos cada, max 5 = 75)
    await asyncio.sleep(RATE_LIMIT)
    tweets = await api.get_user_tweets(username, MAX_TWEETS_PER_USER)
    
    return {
        "username": username,
        "display_name": info.get("name", username),
        "followers": followers,
        "following": info.get("following", 0),
        "tweets_count": current_count,
        "verified": info.get("isBlueVerified", False),
        "location": info.get("location", ""),
        "new_tweets": len(tweets) if has_new else 0,
        "latest_tweets": [
            {
                "id": t.get("id", ""),
                "text": (t.get("text", "") or "")[:200],
                "likes": t.get("likeCount", 0),
                "retweets": t.get("retweetCount", 0),
                "replies": t.get("replyCount", 0),
                "views": t.get("viewCount", 0),
                "created_at": t.get("createdAt", ""),
                "url": t.get("url", f"https://x.com/{username}/status/{t.get('id', '')}"),
            }
            for t in tweets
        ],
    }


# ═══════════════════════════════════════════════
# PIPELINE
# ═══════════════════════════════════════════════

async def run_vip_check() -> str:
    """Checa apenas VIPs — chamado a cada 59min"""
    state = load_state()
    api = TwitterAPI(API_KEY)
    alerts = []
    
    try:
        for username in state["users"]["vip"]:
            result = await check_user(api, username, state, force=False)
            if result:
                tweets_text = "\n".join(
                    f"  ▸ {t['text'][:80]}...\n  ❤️{t['likes']} 🔁{t['retweets']}"
                    for t in result["latest_tweets"][:3]
                )
                alerts.append(
                    f"🔔 *@{username}* postou {result['new_tweets']} novo(s)!\n{tweets_text}"
                )
        save_state(state)
    finally:
        await api.close()
    
    return "\n\n".join(alerts) if alerts else ""


async def run_daily_check() -> str:
    """Checa todos + trending — chamado às 23:55"""
    state = load_state()
    api = TwitterAPI(API_KEY)
    lines = [f"🐦 *Twitter Daily Report* — {datetime.now().strftime('%d/%b/%Y %H:%M')}", ""]
    changes = 0
    calls = 0
    
    try:
        # Trending
        try:
            trends = await api.get_trends(WOEID_GLOBAL)
            lines.append("*🔥 Trending Global:*")
            for i, t in enumerate(trends[:5], 1):
                lines.append(f"  {i}\\. {t.get('name', '?')}")
            calls += 1
            lines.append("")
        except Exception as e:
            lines.append(f"⚠️ Trending: {e}")
        
        try:
            await asyncio.sleep(RATE_LIMIT)
            trends_br = await api.get_trends(WOEID_BRAZIL)
            lines.append("*🇧🇷 Trending Brasil:*")
            for i, t in enumerate(trends_br[:5], 1):
                lines.append(f"  {i}\\. {t.get('name', '?')}")
            calls += 1
            lines.append("")
        except Exception:
            pass
        
        # Todos os users (VIP + Regular)
        all_users = state["users"]["vip"] + state["users"]["regular"]
        
        for username in all_users:
            result = await check_user(api, username, state, force=False)
            calls += 2  # info + optional tweets
            if result:
                changes += 1
                lines.append(f"*@{username}* — {result['followers']:,} followers | +{result['new_tweets']} tweets")
                for t in result["latest_tweets"][:2]:
                    text = (t['text'] or '')[:100].replace('\n', ' ')
                    lines.append(f"  ▸ {text}")
                lines.append("")
        
        save_state(state)
        
        lines.append(f"📊 {changes} users com novidades | ~{calls} chamadas API")
        
    finally:
        await api.close()
    
    return "\n".join(lines)


# ═══════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════

async def main():
    import sys
    mode = sys.argv[1] if len(sys.argv) > 1 else "vip"
    
    if mode == "vip":
        result = await run_vip_check()
        if result:
            print(result)
        else:
            print("VIP_CHECK_OK:NONE")  # sinaliza "sem novidades"
    elif mode == "daily":
        result = await run_daily_check()
        print(result)
        # Save report
        date_str = datetime.now().strftime("%Y-%m-%d")
        (OUTPUT_DIR / f"report-{date_str}.md").write_text(result)
    else:
        print(f"Usage: python3 {sys.argv[0]} [vip|daily]")


if __name__ == "__main__":
    asyncio.run(main())
