#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
changelog_webhook.py

Script simples para consultar a API de change logs (com Basic Auth) e enviar uma embed ao Discord via Webhook.
- Suporta carregar credenciais via VARIÁVEIS DE AMBIENTE ou arquivo .env (opcional, usando python-dotenv).
- Mantém estado em um arquivo JSON para não repostar logs antigos.
- Modo `--once` para execução única (útil para testes / agendamento).

Como usar (resumo):
1) Criar um .env ou definir as variáveis de ambiente abaixo
2) Instalar dependências: pip install requests python-dotenv
3) Rodar: python changelog_webhook.py --once   (teste)
   ou:  python changelog_webhook.py            (loop contínuo)

Variáveis esperadas (exemplos):
  WEBHOOK_URL=https://discord.com/api/webhooks/......
  API_URL=https://api.robotproject.com.br/games/changelog
  API_USERNAME=seu_usuario
  API_PASSWORD=sua_senha
  POLL_INTERVAL=300
  POST_HISTORY_ON_FIRST_RUN=false
  STATE_FILE=changelog_state.json

"""

import os
import time
import json
import argparse
from datetime import datetime, timezone

# tentativa de carregar .env (opcional)
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    # python-dotenv é opcional — o script funcionará lendo variáveis de ambiente diretamente
    pass

import requests

# ---------------- CONFIG (lê das variáveis de ambiente) ----------------
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")
API_URL = os.getenv("API_URL", "")
API_USERNAME = os.getenv("API_USERNAME")
API_PASSWORD = os.getenv("API_PASSWORD")
POLL_INTERVAL = int(os.getenv("POLL_INTERVAL", "300"))  # segundos
STATE_FILE = os.getenv("STATE_FILE", "changelog_state.json")
POST_HISTORY_ON_FIRST_RUN = os.getenv("POST_HISTORY_ON_FIRST_RUN", "false").lower() in ("1", "true", "yes")
RED_COLOR = int(os.getenv("RED_COLOR", "0xFF0000"), 0)
# -----------------------------------------------------------------------


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
    # Normalizar Z -> +00:00
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s)
    except Exception:
        # tentar alguns formatos comuns
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


def build_embed(entry):
    # Campos esperados: Id, CreatedAt, Message (ou id, createdAt, message)
    eid = entry.get("id") or entry.get("Id") or 0
    raw_msg = entry.get("message") or entry.get("Message") or ""
    created = entry.get("createdAt") or entry.get("CreatedAt") or ""

    dt = parse_iso_datetime(created) or datetime.now()
    date_str, time_only = format_local(dt)

    # separar PT e EN por linhas (primeira linha = PT, segunda = EN)
    lines = [ln.strip() for ln in raw_msg.splitlines() if ln.strip()]
    if len(lines) >= 2:
        pt = lines[0]
        en = lines[1]
    else:
        pt = raw_msg
        en = raw_msg

    # agora com @everyone de verdade (ping real)
    field_value = f"🇧🇷 {pt}\n🇺🇸 {en}\n@everyone"

    embed = {
        "title": "📢 Nova atualização",
        "color": RED_COLOR,
        "fields": [
            {"name": "📝 Mensagem", "value": field_value},
            {"name": "⏰ Date", "value": date_str}
        ]
    }

    return embed



def post_embed(embed):
    if not WEBHOOK_URL:
        raise ValueError("WEBHOOK_URL não está configurado")
    payload = {"embeds": [embed]}
    headers = {"Content-Type": "application/json"}
    # nota: se quiser também enviar uma mensagem de texto antes, adicione 'content': "@everyone" (mas evitaremos)
    resp = requests.post(WEBHOOK_URL, json=payload, headers=headers, timeout=15)
    resp.raise_for_status()
    return resp


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


def run_once():
    state = load_state()
    last_id = int(state.get("last_id", 0))
    last_ts = state.get("last_ts")

    data = fetch_changelogs()
    logs = None
    if isinstance(data, dict) and "data" in data:
        logs = data["data"]
    elif isinstance(data, list):
        logs = data
    else:
        logs = []

    if not logs:
        print("Sem changelogs no retorno da API.")
        return

    # ordenar cronologicamente
    def sort_key(e):
        eid = e.get("id") or e.get("Id")
        if eid:
            try:
                return int(eid)
            except Exception:
                pass
        created = parse_iso_datetime(e.get("createdAt") or e.get("CreatedAt") or "")
        return created.timestamp() if created else 0

    logs_sorted = sorted(logs, key=sort_key)
    new_logs = []

    for e in logs_sorted:
        eid = e.get("id") or e.get("Id")
        if eid:
            try:
                if int(eid) > last_id:
                    new_logs.append(e)
            except Exception:
                pass
        else:
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

    # se for primeira execução e POST_HISTORY_ON_FIRST_RUN == False, apenas atualiza estado
    state_changed = False
    if (not state) and (not POST_HISTORY_ON_FIRST_RUN):
        # inicializa last_id para o maior encontrado
        max_id = last_id
        for e in logs_sorted:
            eid = e.get("id") or e.get("Id")
            if eid:
                try:
                    max_id = max(max_id, int(eid))
                except Exception:
                    pass
        state["last_id"] = max_id
        if logs_sorted:
            ts_candidate = logs_sorted[-1].get("createdAt") or logs_sorted[-1].get("CreatedAt")
            if ts_candidate:
                state["last_ts"] = ts_candidate
        save_state(state)
        print("Primeira execução: estado inicializado sem postar históricos.")
        return

    for e in new_logs:
        try:
            embed = build_embed(e)
            post_embed(embed)
            print("Postado changelog id:", e.get("id") or e.get("Id"))
        except Exception as exc:
            print("Erro ao postar embed:", exc)
        # atualizar estado
        eid = e.get("id") or e.get("Id")
        if eid:
            try:
                state["last_id"] = int(eid)
            except Exception:
                pass
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
    parser = argparse.ArgumentParser(description="Webhook changelog poster (com Basic Auth)")
    parser.add_argument("--once", action="store_true", help="Executa apenas uma vez e sai (útil para testes)")
    args = parser.parse_args()

    # checagens rápidas
    if not WEBHOOK_URL:
        print("AVISO: WEBHOOK_URL não configurado. Defina a variável de ambiente WEBHOOK_URL ou crie um .env.")
    if not API_URL:
        print("AVISO: API_URL não configurado. Defina a variável de ambiente API_URL ou crie um .env.")

    if args.once:
        run_once()
    else:
        main_loop()
