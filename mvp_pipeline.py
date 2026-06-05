#!/usr/bin/env python3
"""
Twitter Data Pipeline MVP
===========================
Coleta diária de Trending Topics + Timeline de @users
Stack: twitterapi.io (primary) → twscrape (fallback)

REPO: https://github.com/JonesGit4/twitter-data-pipeline
"""

import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

# ============================================================
# CONFIG
# ============================================================

CONFIG = {
    "twitterapi_key": os.getenv("TWITTERAPI_IO_KEY", "new1_6deba88d9fa94d4d9e01d6fca78fe035"),
    "output_dir": os.path.expanduser("~/.hermes/data/twitter"),
    "woeid_global": 1,
    "woeid_brazil": 455827,
    "monitor_users": [
        "FlavioBolsonaro",
        "elonmusk",
    ],
    "max_tweets_per_user": 5,
    "max_trends": 5,
    "rate_limit_delay": 6.0,  # free tier: 1 req / 5s
}

# ============================================================
# DATA MODELS
# ============================================================

class DailyReport:
    def __init__(self):
        self.timestamp = datetime.now(timezone.utc).isoformat()
        self.trends_global: list[dict] = []
        self.trends_brazil: list[dict] = []
        self.trends_ny: list[dict] = []
        self.users: dict[str, dict] = {}
        self.errors: list[str] = []
        self.source: str = "none"
        self.latency_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "source": self.source,
            "latency_ms": round(self.latency_ms, 0),
            "trends_global": self.trends_global,
            "trends_brazil": self.trends_brazil,
            "trends_ny": self.trends_ny,
            "users": self.users,
            "errors": self.errors,
        }


# ============================================================
# TWITTERAPI.IO CLIENT
# ============================================================

class TwitterAPIIO:
    """Cliente para twitterapi.io — $0.15/1K tweets"""
    
    BASE = "https://api.twitterapi.io/twitter"
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.client = httpx.AsyncClient(
            headers={"X-API-Key": api_key},
            timeout=30.0,
        )
    
    async def get_trends(self, woeid: int = 1) -> list[dict]:
        """GET /twitter/trends?woeid= — retorna trending topics (1=global, 455827=SP)"""
        r = await self.client.get(
            f"{self.BASE}/trends",
            params={"woeid": woeid}
        )
        r.raise_for_status()
        data = r.json()
        raw_trends = data.get("trends", [])
        # Formato: [{"trend": {"name": "...", "rank": 1, "target": {"query": "..."}}}]
        return [t["trend"] for t in raw_trends if "trend" in t]
    
    async def get_user_info(self, username: str) -> dict:
        """GET /twitter/user/info?userName=username"""
        r = await self.client.get(
            f"{self.BASE}/user/info",
            params={"userName": username}
        )
        r.raise_for_status()
        data = r.json()
        # Formato: {"status": "success", "data": {"id": "...", "name": "...", "followers": ...}}
        return data.get("data", data)
    
    async def get_user_tweets(self, username: str, max_tweets: int = 10) -> list[dict]:
        """GET /twitter/user/last_tweets?userName=username"""
        r = await self.client.get(
            f"{self.BASE}/user/last_tweets",
            params={"userName": username}
        )
        r.raise_for_status()
        data = r.json()
        # Formato: {"status": "success", "data": {"tweets": [{...}, ...]}}
        inner = data.get("data", data)
        tweets = inner.get("tweets", []) if isinstance(inner, dict) else []
        return tweets[:max_tweets]
    
    async def advanced_search(self, query: str, limit: int = 10) -> list[dict]:
        """GET /twitter/tweet/advanced_search"""
        r = await self.client.get(
            f"{self.BASE}/tweet/advanced_search",
            params={"query": query, "maxItems": limit}
        )
        r.raise_for_status()
        data = r.json()
        if isinstance(data, list):
            return data[:limit]
        return data.get("tweets", [])[:limit]
    
    async def close(self):
        await self.client.aclose()


# ============================================================
# PIPELINE
# ============================================================

def extract_trends(raw: list[dict], max_items: int = 5) -> list[dict]:
    """Extrai trending topics relevantes — campos reais do twitterapi.io"""
    result = []
    for t in raw[:max_items]:
        result.append({
            "name": t.get("name", "?"),
            "rank": t.get("rank", 0),
            "query": t.get("target", {}).get("query", "") if isinstance(t.get("target"), dict) else "",
        })
    return result


def extract_user_snapshot(username: str, info: dict, tweets: list[dict]) -> dict:
    """Snapshot diário de um @user — campos reais do twitterapi.io"""
    latest_tweets = []
    for t in tweets[:10]:
        latest_tweets.append({
            "id": t.get("id", ""),
            "text": (t.get("text", "") or "")[:200],
            "likes": t.get("likeCount", 0),
            "retweets": t.get("retweetCount", 0),
            "replies": t.get("replyCount", 0),
            "views": t.get("viewCount", 0),
            "created_at": t.get("createdAt", ""),
            "url": t.get("url", f"https://x.com/{username}/status/{t.get('id', '')}"),
        })
    
    return {
        "username": username,
        "display_name": info.get("name", username),
        "followers": info.get("followers", 0),
        "following": info.get("following", 0),
        "tweets_count": info.get("statusesCount", 0),
        "verified": info.get("isBlueVerified", info.get("isVerified", False)),
        "location": info.get("location", ""),
        "description": (info.get("description", "") or "")[:200],
        "latest_tweets": latest_tweets,
    }


async def run_pipeline(config: dict) -> DailyReport:
    """Executa coleta completa de dados"""
    report = DailyReport()
    t0 = time.time()
    
    api_key = config["twitterapi_key"]
    if not api_key:
        report.errors.append("TWITTERAPI_IO_KEY não configurada")
        report.latency_ms = (time.time() - t0) * 1000
        return report
    
    api = TwitterAPIIO(api_key)
    report.source = "twitterapi.io"
    delay = config.get("rate_limit_delay", 6.0)
    
    try:
        # ── Trending Global ──
        try:
            raw_trends = await api.get_trends(config["woeid_global"])
            report.trends_global = extract_trends(raw_trends, config["max_trends"])
            await asyncio.sleep(delay)
        except Exception as e:
            report.errors.append(f"trends_global: {e}")
        
        # ── Trending Brasil ──
        try:
            raw_trends_br = await api.get_trends(config["woeid_brazil"])
            report.trends_brazil = extract_trends(raw_trends_br, config["max_trends"])
            await asyncio.sleep(delay)
        except Exception as e:
            report.errors.append(f"trends_brazil: {e}")
        
        # ── Monitor Users ──
        for username in config["monitor_users"]:
            try:
                await asyncio.sleep(delay)
                info = await api.get_user_info(username)
                await asyncio.sleep(delay)
                tweets = await api.get_user_tweets(username, config["max_tweets_per_user"])
                report.users[username] = extract_user_snapshot(username, info, tweets)
            except Exception as e:
                report.errors.append(f"user:{username}: {e}")
        
    except Exception as e:
        report.errors.append(f"pipeline: {e}")
    finally:
        await api.close()
    
    report.latency_ms = (time.time() - t0) * 1000
    return report


# ============================================================
# OUTPUT
# ============================================================

def save_report(report: DailyReport, config: dict):
    """Salva relatório diário em JSON + Markdown"""
    output_dir = Path(config["output_dir"])
    output_dir.mkdir(parents=True, exist_ok=True)
    
    date_str = datetime.now().strftime("%Y-%m-%d")
    
    # JSON (machine-readable, para histórico)
    json_path = output_dir / f"report-{date_str}.json"
    json_path.write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=False))
    
    # Markdown (human-readable, para Telegram)
    md_path = output_dir / f"report-{date_str}.md"
    md = format_markdown(report)
    md_path.write_text(md)
    
    return json_path, md_path


def format_markdown(report: DailyReport) -> str:
    """Formata relatório em Markdown para Telegram"""
    lines = [
        f"🐦 *Twitter Daily Report* — {datetime.now().strftime('%d/%b/%Y %H:%M')}",
        f"📡 Source: {report.source} | ⏱️ {report.latency_ms:.0f}ms",
        "",
    ]
    
    # Trending Global
    if report.trends_global:
        lines.append("*🔥 Trending Global:*")
        for i, t in enumerate(report.trends_global[:5], 1):
            lines.append(f"  {i}\\. {t['name']}")
        lines.append("")
    
    # Trending Brasil
    if report.trends_brazil:
        lines.append("*🇧🇷 Trending Brasil:*")
        for i, t in enumerate(report.trends_brazil[:5], 1):
            lines.append(f"  {i}\\. {t['name']}")
        lines.append("")
    
    # Users
    if report.users:
        lines.append("*👤 Users Monitorados:*")
        for username, data in report.users.items():
            lines.append(f"  *@{username}* — {data['followers']:,} followers")
            for t in data.get("latest_tweets", [])[:3]:
                text = t['text'].replace('\n', ' ')[:100]
                eng = f"❤️{t['likes']} 🔁{t['retweets']}"
                lines.append(f"    ▸ {text}")
                lines.append(f"    {eng}")
        lines.append("")
    
    # Errors
    if report.errors:
        lines.append("*⚠️ Erros:*")
        for e in report.errors:
            lines.append(f"  • {e}")
    
    # Link repo
    lines.append("")
    lines.append("[📂 Repo](https://github.com/JonesGit4/twitter-data-pipeline)")
    
    return "\n".join(lines)


# ============================================================
# MAIN
# ============================================================

async def main():
    print("╔══════════════════════════════════════════╗")
    print("║  Twitter Data Pipeline — Daily Report   ║")
    print("╚══════════════════════════════════════════╝")
    
    api_key = CONFIG["twitterapi_key"]
    if not api_key:
        print("⚠️  TWITTERAPI_IO_KEY não definida.")
        print("   Exporte: export TWITTERAPI_IO_KEY='your_key'")
        print("   Ou crie conta gratuita em: https://twitterapi.io")
        sys.exit(1)
    
    report = await run_pipeline(CONFIG)
    
    if report.users or report.trends_global:
        json_path, md_path = save_report(report, CONFIG)
        print(f"✅ Relatório salvo:")
        print(f"   JSON: {json_path}")
        print(f"   MD:   {md_path}")
        print(f"   Trends: {len(report.trends_global)} | Users: {len(report.users)}")
    else:
        print("❌ Nenhum dado coletado")
    
    if report.errors:
        print(f"⚠️  {len(report.errors)} erro(s):")
        for e in report.errors:
            print(f"   • {e}")
    else:
        print("✅ Zero erros")
    
    # Print markdown preview
    md = format_markdown(report)
    print("\n── Preview Markdown ──\n")
    print(md)
    
    # Save to stdout for piping
    sys.stdout.flush()

if __name__ == "__main__":
    asyncio.run(main())
