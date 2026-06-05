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
    "twitterapi_key": os.getenv("TWITTERAPI_IO_KEY", ""),
    "output_dir": os.path.expanduser("~/.hermes/data/twitter"),
    "woeid_sao_paulo": 455827,
    "woeid_new_york": 2459115,
    "monitor_users": [
        "elonmusk",
        "naval",
        # Adicione @users aqui
    ],
    "max_tweets_per_user": 10,
    "max_trends": 5,
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
    
    async def get_trends(self) -> list[dict]:
        """GET /twitter/trends — retorna trending topics"""
        r = await self.client.get(f"{self.BASE}/trends")
        r.raise_for_status()
        data = r.json()
        return data if isinstance(data, list) else data.get("trends", [])
    
    async def get_user_info(self, username: str) -> dict:
        """GET /twitter/user/info?userName=username"""
        r = await self.client.get(
            f"{self.BASE}/user/info",
            params={"userName": username}
        )
        r.raise_for_status()
        return r.json()
    
    async def get_user_tweets(self, username: str, max_tweets: int = 10) -> list[dict]:
        """GET /twitter/user/last_tweets?userName=username"""
        r = await self.client.get(
            f"{self.BASE}/user/last_tweets",
            params={"userName": username}
        )
        r.raise_for_status()
        data = r.json()
        if isinstance(data, list):
            return data[:max_tweets]
        tweets = data.get("tweets", data.get("data", []))
        if isinstance(tweets, list):
            return tweets[:max_tweets]
        return []
    
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
    """Extrai trending topics relevantes"""
    result = []
    for t in raw[:max_items]:
        result.append({
            "name": t.get("name", t.get("trend_name", "?")),
            "tweet_volume": t.get("tweet_volume", t.get("volume", 0)),
            "url": t.get("url", ""),
            "query": t.get("query", ""),
            "category": t.get("category", ""),
        })
    return result


def extract_user_snapshot(username: str, info: dict, tweets: list[dict]) -> dict:
    """Snapshot diário de um @user"""
    latest_tweets = []
    for t in tweets[:10]:
        latest_tweets.append({
            "id": t.get("id", t.get("tweet_id", "")),
            "text": (t.get("text", t.get("content", "")) or "")[:200],
            "likes": t.get("likeCount", t.get("favorite_count", 0)),
            "retweets": t.get("retweetCount", t.get("retweet_count", 0)),
            "replies": t.get("replyCount", t.get("reply_count", 0)),
            "views": t.get("viewCount", t.get("view_count", 0)),
            "created_at": t.get("createdAt", t.get("created_at", "")),
            "url": f"https://x.com/{username}/status/{t.get('id', t.get('tweet_id', ''))}",
        })
    
    return {
        "username": username,
        "display_name": info.get("name", info.get("display_name", username)),
        "followers": info.get("followers", info.get("followers_count", 0)),
        "following": info.get("following", info.get("friends_count", 0)),
        "tweets_count": info.get("tweetsCount", info.get("statuses_count", 0)),
        "verified": info.get("verified", info.get("is_verified", False)),
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
    
    try:
        # ── Trending Global ──
        try:
            raw_trends = await api.get_trends()
            report.trends_global = extract_trends(raw_trends, config["max_trends"])
        except Exception as e:
            report.errors.append(f"trends_global: {e}")
        
        # ── Monitor Users ──
        for username in config["monitor_users"]:
            try:
                info = await api.get_user_info(username)
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
            vol = f"{t['tweet_volume']:,}" if t['tweet_volume'] else "?"
            lines.append(f"  {i}\\. {t['name']} \\({vol} tweets\\)")
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
