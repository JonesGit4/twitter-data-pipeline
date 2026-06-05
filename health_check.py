#!/usr/bin/env python3
"""
Twitter Pipeline — Health Check & Fallback
===========================================
Verifica se twitterapi.io está respondendo.
Se falhar, tenta twscrape como fallback.

Uso: python3 health_check.py
Saída: JSON com status + dados se disponível
"""

import asyncio
import json
import os
import sys
import time
from datetime import datetime, timezone

import httpx


async def check_twitterapi_io(api_key: str) -> dict:
    """Verifica se twitterapi.io está funcional"""
    result = {"provider": "twitterapi.io", "status": "unknown", "latency_ms": 0, "data": None, "error": None}
    
    if not api_key:
        result["status"] = "unconfigured"
        result["error"] = "TWITTERAPI_IO_KEY not set"
        return result
    
    t0 = time.time()
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            r = await client.get(
                "https://api.twitterapi.io/twitter/trends",
                headers={"X-API-Key": api_key},
            )
            result["latency_ms"] = (time.time() - t0) * 1000
            
            if r.status_code == 200:
                data = r.json()
                trends = data if isinstance(data, list) else data.get("trends", [])
                result["status"] = "healthy"
                result["data"] = {
                    "trends_count": len(trends),
                    "top_trend": trends[0].get("name", "?") if trends else None,
                }
            elif r.status_code == 401:
                result["status"] = "unauthorized"
                result["error"] = "Invalid API key"
            elif r.status_code == 429:
                result["status"] = "rate_limited"
                result["error"] = f"Rate limited (HTTP {r.status_code})"
            else:
                result["status"] = "degraded"
                result["error"] = f"HTTP {r.status_code}: {r.text[:200]}"
    except httpx.TimeoutException:
        result["status"] = "timeout"
        result["latency_ms"] = (time.time() - t0) * 1000
        result["error"] = "Request timeout"
    except Exception as e:
        result["status"] = "down"
        result["latency_ms"] = (time.time() - t0) * 1000
        result["error"] = str(e)[:200]
    
    return result


async def check_twscrape() -> dict:
    """Verifica se twscrape está configurado e funcional"""
    result = {"provider": "twscrape", "status": "unknown", "latency_ms": 0, "data": None, "error": None}
    
    try:
        from twscrape import API
        
        t0 = time.time()
        api = API()
        
        # Check if any accounts are configured
        pool = api.pool
        active = getattr(pool, 'accounts', [])
        
        if not active:
            result["status"] = "unconfigured"
            result["error"] = "No accounts configured. Use: twscrape add_accounts"
            return result
        
        # Try to get trends
        trends = []
        async for t in api.trends("trending", limit=3):
            trends.append(t.name)
        
        result["latency_ms"] = (time.time() - t0) * 1000
        
        if trends:
            result["status"] = "healthy"
            result["data"] = {"trends_count": len(trends), "top_trend": trends[0]}
        else:
            result["status"] = "degraded"
            result["error"] = "No trends returned"
            
    except ImportError:
        result["status"] = "not_installed"
        result["error"] = "twscrape not installed. Run: pip install twscrape"
    except Exception as e:
        result["status"] = "down"
        result["error"] = str(e)[:200]
    
    return result


async def main():
    api_key = os.getenv("TWITTERAPI_IO_KEY", "")
    
    results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "checks": [],
        "overall": "unknown",
    }
    
    # Check primary
    primary = await check_twitterapi_io(api_key)
    results["checks"].append(primary)
    
    # Check fallback
    fallback = await check_twscrape()
    results["checks"].append(fallback)
    
    # Determine overall status
    if primary["status"] == "healthy":
        results["overall"] = "healthy"
    elif fallback["status"] == "healthy":
        results["overall"] = "degraded_using_fallback"
    elif primary["status"] in ("unconfigured",) and fallback["status"] in ("unconfigured", "not_installed"):
        results["overall"] = "not_configured"
    else:
        results["overall"] = "down"
    
    print(json.dumps(results, indent=2, ensure_ascii=False))
    
    # Exit code for cron monitoring
    if results["overall"] in ("healthy", "degraded_using_fallback"):
        sys.exit(0)
    else:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
