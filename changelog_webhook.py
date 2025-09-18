#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
changelog_webhook.py

Script que consulta a API de change logs e envia mensagens no Discord via Webhook.
Suporta execução única (--once) ou em loop contínuo.

Variáveis de ambiente necessárias:
  WEBHOOK_URL=https://discord.com/api/webhooks/......
  API_URL=https://sua.api/changelog
"""

import os
import time
import requests
import argparse
from datetime import datetime


# ---------------- CONFIG ----------------
API_URL = os.getenv("API_URL")
WEBHOOK_URL = os.getenv("WEBHOOK_URL") or os.getenv("DISCORD_WEBHOOK")

if not API_URL:
    raise ValueError("API_URL não está configurado")
if not WEBHOOK_URL:
    print("⚠️ Nenhum webhook configurado! Defina WEBHOOK_URL ou DISCORD_WEBHOOK.")


# ---------------- FUNÇÕES ----------------
def fetch_changelogs():
    """Busca os changelogs da API"""
    try:
        response = requests.get(API_URL, timeout=15)
        if response.status_code == 200:
            return response.json()
        else:
            print("Erro ao buscar changelogs:", response.text)
            return []
    except Exception as e:
        print("Erro de conexão com API:", e)
        return []


def send_to_discord(entry):
    """Monta e envia embed para o Discord"""

    # Pegando mensagens PT e EN (cada uma separada)
    message_pt = entry.get("message_pt") or "Mensagem PT não encontrada"
    message_en = entry.get("message_en") or "Message EN not found"

    created_at = entry.get("createdAt", datetime.utcnow().isoformat())

    embed = {
        "title": "📢 Nova atualização",
        "color": 0xFF0000,  # Vermelho
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
            "text": "© 2025 General Store | @everyone"
        }
    }

    payload = {"embeds": [embed]}

    try:
        response = requests.post(WEBHOOK_URL, json=payload, timeout=15)
        if response.status_code == 204:
            print("✅ Mensagem enviada com sucesso para o Discord!")
        else:
            print("⚠️ Erro ao enviar mensagem para o Discord:", response.text)
    except Exception as e:
        print("❌ Erro na requisição do Discord:", e)


def run_once():
    """Executa apenas uma vez"""
    data = fetch_changelogs()
    if not data:
        print("Nenhum changelog encontrado.")
        return

    for entry in data:
        print("🔍 DEBUG changelog recebido:", entry)
        try:
            send_to_discord(entry)
            print("Postado changelog id:", entry.get("id"))
        except Exception as exc:
            print("Erro ao postar embed:", exc)


def run_loop():
    """Executa continuamente"""
    print("[Square Cloud Realtime] Connection stablished! 😏")
    print("Iniciando loop -- pressione Ctrl+C para parar")
    ultimo_estado = None

    while True:
        data = fetch_changelogs()
        if data:
            novos = []
            for entry in data:
                entry_id = entry.get("id") or entry.get("createdAt")
                if ultimo_estado is None or entry_id not in ultimo_estado:
                    novos.append(entry)

            for e in novos:
                try:
                    send_to_discord(e)
                    print("Postado changelog id:", e.get("id"))
                except Exception as exc:
                    print("Erro ao postar embed:", exc)

            ultimo_estado = {e.get("id") or e.get("createdAt") for e in data}
            print("Estado atualizado.")

        time.sleep(10)


# ---------------- MAIN ----------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Webhook de changelog para Discord")
    parser.add_argument("--once", action="store_true", help="Executa apenas uma vez e sai")
    args = parser.parse_args()

    if args.once:
        run_once()
    else:
        run_loop()
