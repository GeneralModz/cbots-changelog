#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
changelog_webhook.py
Consulta API de changelogs e posta embeds no Discord via webhook.
Agora adiciona tradução automática com deep-translator e garante 🇧🇷/🇺🇸 sempre.
"""

import os
import time
import json
import argparse
import re
import requests
from datetime import datetime, timezone, timedelta
from deep_translator import GoogleTranslator  # ✅ tradutor

# tenta carregar .env local (opcional)
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# ---------------- CONFIG ----------------
WEBHOOK_URL = os.getenv("WEBHOOK_URL") or os.getenv("DISCORD_WEBHOOK") or ""
API_URL = os.getenv("API_URL") or ""
API_USERNAME = os.getenv("API_USERNAME")
API_PASSWORD = os.getenv("API_PASSWORD")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "60"))
STATE_FILE = os.getenv("STATE_FILE", "changelog_state.json")
POST_HISTORY_ON_FIRST_RUN = os.getenv("POST_HISTORY_ON_FIRST_RUN", "false").lower() in ("1", "true", "yes")
RED_COLOR = int(os.getenv("RED_COLOR", "0xFF0000"), 0)
FOOTER_TEXT = os.getenv("FOOTER_TEXT", "© 2025 General Store")

# Timezone Brasília
BRASILIA_TZ = timezone(timedelta(hours=-3))

# ---------------- helpers ----------------
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
        now = datetime.now(BRASILIA_TZ)
        return now.strftime("%d/%m/%Y, %H:%M:%S"), now.strftime("%H:%M")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc).astimezone(BRASILIA_TZ)
    else:
        dt = dt.astimezone(BRASILIA_TZ)
    return dt.strftime("%d/%m/%Y, %H:%M:%S"), dt.strftime("%H:%M")

def split_game_and_text(msg):
    if not msg:
        return None, None
    m = re.match(r'^\s*\[([^\]]+)\]\s*[-–:]\s*(.*)', msg)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    m2 = re.match(r'^\s*\[([^\]]+)\]\s*(.*)', msg)
    if m2:
        return m2.group(1).strip(), m2.group(2).strip()
    return None, msg.strip()

# ---------------- tradução automática ----------------
def traduzir_texto(texto, alvo):
    try:
        return GoogleTranslator(source="auto", target=alvo).translate(texto)
    except Exception as e:
        print(f"⚠️ Erro ao traduzir '{texto[:30]}...':", e)
        return texto  # fallback: devolve original

# ---------------- build embed ----------------
def build_embed(entry):
    # tenta pegar mensagens direto da API
    message_pt = entry.get("message_pt") or entry.get("mensagem_pt")
    message_en = entry.get("message_en") or entry.get("mensagem_en")
    message = entry.get("message") or entry.get("msg")

    # sempre garante os dois idiomas
    if not message_pt and message_en:
        message_pt = traduzir_texto(message_en, "pt")
    if not message_en and message_pt:
        message_en = traduzir_texto(message_pt, "en")
    if not message_pt and not message_en and message:
        message_pt = traduzir_texto(message, "pt")
        message_en = traduzir_texto(message, "en")

    # nome do jogo
    game_name = entry.get("game") or entry.get("Game")
    if not game_name and message:
        gn, _ = split_game_and_text(message)
        if gn:
            game_name = gn

    # monta valor
    if game_name:
        valor_pt = f"🇧🇷 [{game_name}] - {message_pt}"
        valor_en = f"🇺🇸 [{game_name}] - {message_en}"
    else:
        valor_pt = f"🇧🇷 {message_pt}"
        valor_en = f"🇺🇸 {message_en}"

    # data
    created_at = entry.get("createdAt") or entry.get("CreatedAt") or entry.get("date")
    if created_at:
        dt = parse_iso_datetime(created_at)
        created_fmt = format_local(dt)[0] if dt else created_at
    else:
        created_fmt = datetime.now(BRASILIA_TZ).strftime("%d/%m/%Y, %H:%M:%S")

    embed = {
        "title": "📢 Nova atualização",
        "color": RED_COLOR,
        "fields": [
            {"name": "📝 Mensagem", "value": f"{valor_pt}\n{valor_en}", "inline": False},
            {"name": "⏰ Date", "value": created_fmt, "inline": False}
        ],
        "footer": {"text": FOOTER_TEXT}
    }
    return embed

# ---------------- posting ----------------
def post_embed_then_mention(entry):
    if not WEBHOOK_URL:
        print("Erro: WEBHOOK_URL não configurado.")
        return

    embed = build_embed(entry)
    payload_embed = {"embeds": [embed]}
    r = requests.post(WEBHOOK_URL, json=payload_embed, timeout=15)

    if r.status_code not in (200, 204):
        print("Erro ao postar embed:", r.status_code, r.text[:400])
        return
    print("✅ Embed enviado com sucesso.")

    payload_mention = {"content": "@everyone", "allowed_mentions": {"parse": ["everyone"]}}
    time.sleep(0.35)
    requests.post(WEBHOOK_URL, json=payload_mention, timeout=10)

# ---------------- fetch changelogs ----------------
def fetch_changelogs():
    if not API_URL:
        raise ValueError("API_URL não está configurado")
    headers = {"Accept": "application/json"}
    if API_USERNAME and API_PASSWORD:
        resp = requests.get(API_URL, headers=headers, auth=(API_USERNAME, API_PASSWORD), timeout=15)
    else:
        resp = requests.get(API_URL, headers=headers, timeout=15)
    if resp.status_code != 200:
        print("Erro ao buscar changelogs:", resp.status_code, resp.text[:200])
        return []
    return resp.json()

# ---------------- main loop ----------------
def run_once():
    state = load_state()
    last_ts = state.get("last_ts")
    data = fetch_changelogs()
    logs = data["data"] if isinstance(data, dict) and "data" in data else data if isinstance(data, list) else []

    if not logs:
        print("Sem changelogs no retorno da API.")
        return

    logs_sorted = sorted(logs, key=lambda e: parse_iso_datetime(e.get("createdAt") or e.get("CreatedAt") or "") or datetime.min)
    new_logs = []
    for e in logs_sorted:
        created = parse_iso_datetime(e.get("createdAt") or e.get("CreatedAt") or "")
        if created and (not last_ts or created > parse_iso_datetime(last_ts)):
            new_logs.append(e)

    if not new_logs:
        print("Sem novos changelogs.")
        return

    if (not load_state()) and (not POST_HISTORY_ON_FIRST_RUN):
        last = logs_sorted[-1]
        state = {"last_ts": last.get("createdAt") or last.get("CreatedAt")}
        save_state(state)
        print("Primeira execução: estado inicializado sem postar históricos.")
        return

    for e in new_logs:
        post_embed_then_mention(e)
        if e.get("createdAt") or e.get("CreatedAt"):
            state["last_ts"] = e.get("createdAt") or e.get("CreatedAt")
            save_state(state)

def run_loop():
    print("[Square Cloud Realtime] Conexão estabelecida! 😏")
    while True:
        try:
            run_once()
        except Exception as e:
            print("Erro no loop:", e)
        time.sleep(POLL_INTERVAL)

# ---------------- CLI ----------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Executa uma vez e sai (teste)")
    args = parser.parse_args()

    if args.once:
        run_once()
    else:
        run_loop()
