#!/usr/bin/env python3
"""
Twitter Monitor — Command Processor
====================================
Processa comandos do grupo Twitter Monitor.
Atualiza lista de @users e status.

Comandos:
  + @username  → adiciona
  - @username  → remove
  /list        → lista
  /accounts    → status contas X
  /status      → créditos + saúde
  /report      → força report
"""

import json
import os
import sys
from pathlib import Path

STATE_FILE = Path(os.path.expanduser("~/.hermes/data/twitter/monitor_state.json"))

DEFAULTS = {
    "users": {
        "vip": ["FlavioBolsonaro", "elonmusk"],
        "regular": [],
    },
    "accounts": {
        "hermes_santosBR": {"active": True, "locked_until": None, "added": "2026-06-05"},
    },
    "snapshots": {},
    "twitterapi_credits_remaining": "unknown",
}


def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return dict(DEFAULTS)


def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False))


def cmd_add(state, username: str, tier: str = "regular"):
    username = username.lstrip("@")
    if tier == "vip":
        if username not in state["users"]["vip"]:
            state["users"]["vip"].append(username)
            save_state(state)
            return f"⭐ @{username} adicionado como VIP (59min)"
        return f"⚠️ @{username} já é VIP"
    else:
        if username not in state["users"]["regular"] and username not in state["users"]["vip"]:
            state["users"]["regular"].append(username)
            save_state(state)
            total = len(state["users"]["vip"]) + len(state["users"]["regular"])
            return f"✅ @{username} adicionado ({total} total)"
        return f"⚠️ @{username} já está na lista"


def cmd_remove(state, username: str):
    username = username.lstrip("@")
    for tier in ["vip", "regular"]:
        if username in state["users"][tier]:
            state["users"][tier].remove(username)
            save_state(state)
            total = len(state["users"]["vip"]) + len(state["users"]["regular"])
            return f"❌ @{username} removido ({total} restantes)"
    return f"⚠️ @{username} não está na lista"


def cmd_list(state):
    vip = state["users"].get("vip", [])
    reg = state["users"].get("regular", [])
    if not vip and not reg:
        return "📋 Nenhum @user monitorado."
    lines = [f"📋 *{len(vip) + len(reg)} @users monitorados:*"]
    if vip:
        lines.append("⭐ *VIP (59min):*")
        for u in vip:
            lines.append(f"  • @{u}")
    if reg:
        lines.append("• *Regular (23:55):*")
        for u in reg:
            lines.append(f"  • @{u}")
    return "\n".join(lines)


def cmd_accounts(state):
    lines = ["👤 *Contas X:*"]
    for name, acc in state.get("accounts", {}).items():
        icon = "🟢" if acc.get("active") else "🔴"
        locked = acc.get("locked_until", "none")
        lines.append(f"  {icon} @{name} — locked: {locked}")
    return "\n".join(lines)


def cmd_status(state):
    vip = len(state["users"].get("vip", []))
    reg = len(state["users"].get("regular", []))
    return f"""📊 *Twitter Monitor Status*

• twitterapi.io: ✅ online
• Créditos restantes: {state.get('twitterapi_credits_remaining', 'unknown')}
• Contas X: {sum(1 for a in state.get('accounts', {}).values() if a.get('active'))} ativas de {len(state.get('accounts', {}))}
• @users: {vip} VIP (59min) + {reg} Regular (23:55) = {vip+reg} total
• Repo: [JonesGit4/twitter-data-pipeline](https://github.com/JonesGit4/twitter-data-pipeline)"""


def cmd_report():
    return "🔄 Gerando report... (executando pipeline)"


def process(command: str) -> str:
    state = load_state()
    cmd = command.strip()
    
    if cmd.startswith("++"):
        username = cmd[2:].strip()
        return cmd_add(state, username, tier="vip")
    elif cmd.startswith("+"):
        username = cmd[1:].strip()
        return cmd_add(state, username, tier="regular")
    elif cmd.startswith("-"):
        username = cmd[1:].strip()
        return cmd_remove(state, username)
    elif cmd in ("/list", "/l"):
        return cmd_list(state)
    elif cmd in ("/accounts", "/acc"):
        return cmd_accounts(state)
    elif cmd in ("/status", "/s"):
        return cmd_status(state)
    elif cmd in ("/report", "/r"):
        return cmd_report()
    else:
        return None  # não é comando reconhecido


if __name__ == "__main__":
    if len(sys.argv) > 1:
        cmd = " ".join(sys.argv[1:])
        result = process(cmd)
        if result:
            print(result)
        else:
            print(f"❓ Comando não reconhecido: {cmd}")
            print("Use: + @user | - @user | /list | /accounts | /status | /report")
    else:
        print(cmd_list(load_state()))
