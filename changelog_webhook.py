#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
changelog_webhook.py
Bot que consulta uma API de change logs e posta no Discord via Webhook.
"""

import os
import time
import json
import argparse
from datetime import datetime, timezone, timedelta

# tenta carregar .env
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

import requests

# ---------------- CONFIG ----------------
WEBHOOK_URL = os.getenv("WEBHOOK_URL") or os.getenv("DISCORD_WEBHOOK")
if not WEBHOOK_URL:
    print("⚠️ Nenhum webhook configurado! Defina WEBHOOK_URL ou DISCORD_WEBHOOK.")

API_URL = os.getenv("API_URL", "")
API_USERNAME = os.getenv("API_USERNAME")
API_PASSWORD = os.getenv("API_PASSWORD")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "300"))
STATE_FILE = os.getenv("STATE_FILE", "changelog_state.json")
POST_HISTORY_ON_FIRST_RUN = os.getenv("POST_HISTORY_ON_FIRST_RUN", "false").lower() in ("1", "true", "yes")
RED_COLOR = int(os.getenv("RED_COLOR", "0xFF0000"), 0)

# ---------------- FUNÇÕES AUX ----------------
def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_state(state):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print("Erro salvando estado:", e)

def parse_iso_datetime(s):
    if not s:
        return None
    s = s.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s)
    except Exception:
        for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(s, fmt)
            except Exception:
                pass
    return None

def format_local(dt):
    if dt is None:
        now = datetime.now()
        return now.strftime("%d/%m/%Y, %H:%M:%S"), now.strftime("%H:%M")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc).astimezone()
    else:
        dt = dt.astimezone()
    return dt.strftime("%d/%m/%Y, %H:%M:%S"), dt.strftime("%H:%M")

# ---------------- EMBED ----------------
BRASILIA_TZ = timezone(timedelta(hours=-3))

def send_to_discord(entry):
    import requests
    from datetime import datetime

    webhook_url = os.getenv("WEBHOOK_URL") or os.getenv("DISCORD_WEBHOOK")
    if not webhook_url:
        print("⚠️ Nenhum webhook configurado! Defina WEBHOOK_URL ou DISCORD_WEBHOOK.")
        return

    # Pegando mensagens PT e EN
    message_pt = entry.get("message_pt") or entry.get("message") or "Mensagem PT não encontrada"
    message_en = entry.get("message_en") or entry.get("message") or "Message EN not found"

    created_at = entry.get("createdAt", datetime.utcnow().isoformat())

    embed = {
        "title": "📢 Nova atualização",
        "color": 0xFF0000,  # vermelho
        "fields": [
            {
                "name": "📑 Mensagem",
                "value": f"🇧🇷 {message_pt}\n🇺🇸 {message_en}",
                "inline": False
            },
            {
                "name": "⏰ Date",
                "value": created_at.replace("T", " ").replace("Z", ""),
                "inline": False
            }
        ],
        "footer": {
            "text": "© 2025 General Store"
        }
    }

    payload = {
        "content": "@everyone",  # aqui o mention é real e funcional
        "embeds": [embed]
    }

    try:
        response = requests.post(webhook_url, json=payload)
        if response.status_code == 204:
            print("✅ Mensagem enviada com sucesso para o Discord!")
        else:
            print("⚠️ Erro ao enviar mensagem para o Discord:", response.text)
    except Exception as e:
        print("❌ Erro na requisição do Discord:", e)


# ---------------- API ----------------
def fetch_changelogs():
    if not API_URL:
        raise ValueError("API_URL não está configurado")
    headers = {"Content-Type": "application/json"}
    if API_USERNAME and API_PASSWORD:
        resp = requests.get(API_URL, headers=headers, auth=(API_USERNAME, API_PASSWORD), timeout=15)
    else:
        resp = requests.get(API_URL, headers=headers, timeout=15)
    resp.raise_for_status()
    return resp.json()

# ---------------- EXECUÇÃO ----------------
def run_once():
    state = load_state()
    last_ts = state.get("last_ts")

    data = fetch_changelogs()
    logs = data["data"] if isinstance(data, dict) and "data" in data else data

    if not logs:
        print("Sem changelogs no retorno da API.")
        return

    def sort_key(e):
        created = parse_iso_datetime(e.get("createdAt") or e.get("CreatedAt") or "")
        return created.timestamp() if created else 0

    logs_sorted = sorted(logs, key=sort_key)
    new_logs = []

    for e in logs_sorted:
        created = parse_iso_datetime(e.get("createdAt") or e.get("CreatedAt") or "")
        if created:
            if not last_ts:
                new_logs.append(e)
            else:
                last_ts_dt = parse_iso_datetime(last_ts)
                if last_ts_dt is None or created > last_ts_dt:
                    new_logs.append(e)

    if not new_logs:
        print("Sem novos changelogs.")
        return

    state_changed = False
    if (not state) and (not POST_HISTORY_ON_FIRST_RUN):
        last = logs_sorted[-1]
        state["last_ts"] = last.get("createdAt") or last.get("CreatedAt")
        save_state(state)
        print("Primeira execução: estado inicializado sem postar históricos.")
        return

    for e in new_logs:
        try:
            send_to_discord(e)
            print("Postado changelog:", e.get("message"))
        except Exception as exc:
            print("Erro ao postar embed:", exc)

        if e.get("createdAt") or e.get("CreatedAt"):
            state["last_ts"] = e.get("createdAt") or e.get("CreatedAt")
        save_state(state)
        state_changed = True

    if state_changed:
        print("Estado atualizado.")

def main_loop():
    print("Iniciando loop — pressione Ctrl+C para parar")
    while True:
        try:
            run_once()
        except Exception as e:
            print("Erro no loop:", e)
        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Webhook changelog poster")
    parser.add_argument("--once", action="store_true", help="Executa apenas uma vez e sai")
    args = parser.parse_args()

    if not WEBHOOK_URL:
        print("AVISO: WEBHOOK_URL não configurado.")
    if not API_URL:
        print("AVISO: API_URL não configurado.")

    if args.once:
        run_once()
    else:
        main_loop()

# ---------------- AUTO RESTART ----------------
import threading
AUTO_RESTART_MINUTES = 1440

def auto_restart():
    print("⏳ Reiniciando automaticamente para liberar memória...")
    os._exit(0)

if AUTO_RESTART_MINUTES > 0:
    t = threading.Timer(AUTO_RESTART_MINUTES * 60, auto_restart)
    t.daemon = True
    t.start()
