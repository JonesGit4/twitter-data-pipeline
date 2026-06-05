#!/usr/bin/env python3
"""
twscrape Account Setup
======================
Script para configurar contas X/Twitter no twscrape.
Execute quando tiver as 3 contas descartáveis prontas.

Uso: python3 setup_twscrape.py accounts.json

accounts.json:
{
  "accounts": [
    {"username": "user1", "password": "pass1", "email": "email1@example.com", "email_password": "pass1"},
    ...
  ]
}
"""

import asyncio
import json
import sys
from pathlib import Path


async def setup_accounts(accounts_file: str):
    """Adiciona contas ao pool do twscrape"""
    from twscrape import API
    
    with open(accounts_file) as f:
        config = json.load(f)
    
    accounts = config.get("accounts", [])
    if not accounts:
        print("❌ Nenhuma conta encontrada no JSON")
        sys.exit(1)
    
    print(f"🔧 Configurando {len(accounts)} conta(s) no twscrape...")
    api = API()
    
    for i, acc in enumerate(accounts, 1):
        username = acc["username"]
        password = acc["password"]
        email = acc.get("email", "")
        email_password = acc.get("email_password", "")
        
        print(f"  [{i}/{len(accounts)}] Adicionando @{username}...")
        
        try:
            await api.pool.add_account(
                username=username,
                password=password,
                email=email,
                email_password=email_password,
            )
            print(f"    ✅ @{username} adicionada")
        except Exception as e:
            print(f"    ❌ @{username} falhou: {e}")
    
    # Save sessions
    print(f"\n💾 Sessões salvas em: {Path.cwd() / 'accounts.db'}")
    print("✅ Setup completo. Execute 'python3 health_check.py' para verificar.")


async def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    await setup_accounts(sys.argv[1])


if __name__ == "__main__":
    asyncio.run(main())
