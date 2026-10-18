#!/usr/bin/env python3
import os
import sys
import json
import urllib.request
import urllib.error
from datetime import datetime

ENV_PATH = "/home/biezz/.hermes/.env"

def get_env_var(key: str) -> str:
    val = os.environ.get(key)
    if val:
        return val
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH) as f:
            for line in f:
                line = line.strip()
                if line.startswith(f"{key}="):
                    return line.split("=", 1)[1].strip().strip("\"'")
    return ""

def send_discord_thread(thread_id: str, title: str, status: str, task: str, findings: str = "Normal", blocker: str = "None", next_step: str = "-", color: int = 3066993) -> bool:
    token = get_env_var("DISCORD_BOT_TOKEN")
    if not token:
        print("[ERROR] DISCORD_BOT_TOKEN not found", file=sys.stderr)
        return False
    
    status_colors = {
        "MULAI": 3447003,        # Blue
        "SEDANG BERJALAN": 16776960, # Yellow
        "SELESAI": 3066993,      # Green
        "VALIDATED": 3066993,    # Green
        "BLOCKER": 15158332,     # Red
        "GAGAL": 15158332        # Red
    }
    chosen_color = status_colors.get(status.upper(), color)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S WIB")

    embed = {
        "title": title,
        "color": chosen_color,
        "fields": [
            {"name": "Status", "value": f"**{status}**", "inline": True},
            {"name": "Task", "value": task, "inline": True},
            {"name": "Temuan / Hasil", "value": findings, "inline": False},
            {"name": "Blocker", "value": blocker, "inline": True},
            {"name": "Lanjut Ke", "value": next_step, "inline": True}
        ],
        "footer": {"text": f"Orchestrator LGP | {now_str}"}
    }

    url = f"https://discord.com/api/v10/channels/{thread_id}/messages"
    data = json.dumps({"embeds": [embed]}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bot {token}",
            "Content-Type": "application/json",
            "User-Agent": "HermesDiscordBot (1.0)"
        }
    )
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status in (200, 201)
    except urllib.error.HTTPError as e:
        print(f"[ERROR] Discord post failed: {e.code} - {e.read().decode('utf-8', errors='ignore')}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"[ERROR] Discord post exception: {e}", file=sys.stderr)
        return False

def send_slack_report(channel_id: str, text: str, blocks: object = None) -> bool:
    token = get_env_var("SLACK_BOT_TOKEN")
    if not token:
        print("[ERROR] SLACK_BOT_TOKEN not found", file=sys.stderr)
        return False

    payload: dict[str, object] = {"channel": channel_id, "text": text}
    if blocks:
        payload["blocks"] = blocks

    url = "https://slack.com/api/chat.postMessage"
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
    )
    try:
        with urllib.request.urlopen(req) as resp:
            res_data = json.loads(resp.read().decode("utf-8"))
            if not res_data.get("ok"):
                print(f"[ERROR] Slack post failed: {res_data.get('error')}", file=sys.stderr)
                return False
            return True
    except Exception as e:
        print(f"[ERROR] Slack post exception: {e}", file=sys.stderr)
        return False

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Multi-platform notifier for Discord & Slack")
    subparsers = parser.add_subparsers(dest="target")

    d_parser = subparsers.add_parser("discord")
    d_parser.add_argument("--thread-id", required=True)
    d_parser.add_argument("--title", required=True)
    d_parser.add_argument("--status", default="SEDANG BERJALAN")
    d_parser.add_argument("--task", required=True)
    d_parser.add_argument("--findings", default="Normal")
    d_parser.add_argument("--blocker", default="Tidak ada")
    d_parser.add_argument("--next-step", default="-")

    s_parser = subparsers.add_parser("slack")
    s_parser.add_argument("--channel-id", default="C0BV1LWFVB5")
    s_parser.add_argument("--text", required=True)

    args = parser.parse_args()
    if args.target == "discord":
        ok = send_discord_thread(
            thread_id=args.thread_id,
            title=args.title,
            status=args.status,
            task=args.task,
            findings=args.findings,
            blocker=args.blocker,
            next_step=args.next_step
        )
        sys.exit(0 if ok else 1)
    elif args.target == "slack":
        ok = send_slack_report(args.channel_id, args.text)
        sys.exit(0 if ok else 1)
    else:
        parser.print_help()
