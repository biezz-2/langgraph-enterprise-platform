#!/usr/bin/env python3
"""Automated Token Rotation and Lifecycle CLI for Secure MCP Ingress.

Usage:
  python3 auth/rotate_tokens.py --rotate --client-id <client_id> [--grace-hours 24]
  python3 auth/rotate_tokens.py --create --client-id <client_id> --scopes memory:read,tools:execute
  python3 auth/rotate_tokens.py --revoke-client <client_id> --reason "Compromised credential"
  python3 auth/rotate_tokens.py --list [--client-id <client_id>]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure package import works when script run directly
repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from auth.token_manager import (
    DEFAULT_EXPIRY_DAYS,
    DEFAULT_GRACE_HOURS,
    DEFAULT_RESOURCE_AUD,
    SUPPORTED_SCOPES,
    TokenManager,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Secure MCP Ingress Token Rotation CLI")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--rotate", action="store_true", help="Rotate token for a client")
    group.add_argument("--create", action="store_true", help="Create initial token for a client")
    group.add_argument("--revoke-client", type=str, metavar="CLIENT_ID", help="Revoke all tokens for a client")
    group.add_argument("--revoke-hash", type=str, metavar="TOKEN_HASH", help="Revoke token by SHA-256 hash")
    group.add_argument("--list", action="store_true", help="List token records")

    parser.add_argument("--client-id", type=str, help="Client ID for token operations")
    parser.add_argument("--scopes", type=str, default="memory:read,memory:write,tools:execute",
                        help="Comma-separated scopes (default: all supported scopes)")
    parser.add_argument("--aud", type=str, default=DEFAULT_RESOURCE_AUD, help="Audience URI")
    parser.add_argument("--grace-hours", type=int, default=DEFAULT_GRACE_HOURS,
                        help="Grace period hours for old token (default: 24)")
    parser.add_argument("--expiry-days", type=int, default=DEFAULT_EXPIRY_DAYS,
                        help="Token expiration days (default: 90)")
    parser.add_argument("--description", type=str, default="", help="Description/metadata")
    parser.add_argument("--reason", type=str, default="Emergency revocation", help="Revocation reason")
    parser.add_argument("--store-path", type=str, default=None, help="Custom path to tokens_store.json")

    args = parser.parse_args()
    tm = TokenManager(store_path=args.store_path)

    if args.rotate:
        if not args.client_id:
            print("[ERROR] --client-id is required for --rotate", file=sys.stderr)
            return 1
        try:
            new_raw_token, new_hash, new_rec = tm.rotate_token(
                client_id=args.client_id,
                grace_hours=args.grace_hours,
                expires_in_days=args.expiry_days,
            )
            print("==================================================")
            print("TOKEN ROTATION COMPLETED SUCCESSFULLY")
            print("==================================================")
            print(f"Client ID:       {args.client_id}")
            print(f"Grace Period:    {args.grace_hours} jam untuk token aktif sebelumnya")
            print(f"New Token Hash:  {new_hash}")
            print(f"Scopes:          {', '.join(new_rec['scopes'])}")
            print(f"Audience:        {new_rec['aud']}")
            print(f"Expires At:      {new_rec['expires_at']}")
            print("--------------------------------------------------")
            print("NEW RAW TOKEN (Save immediately; not stored in plaintext):")
            print(new_raw_token)
            print("==================================================")
            return 0
        except Exception as e:
            print(f"[ERROR] Rotation failed: {e}", file=sys.stderr)
            return 1

    if args.create:
        if not args.client_id:
            print("[ERROR] --client-id is required for --create", file=sys.stderr)
            return 1
        raw_scopes = [s.strip() for s in args.scopes.split(",") if s.strip()]
        for s in raw_scopes:
            if s not in SUPPORTED_SCOPES:
                print(f"[ERROR] Unsupported scope: {s}. Valid: {sorted(SUPPORTED_SCOPES)}", file=sys.stderr)
                return 1
        raw_token, record = tm.create_token(
            client_id=args.client_id,
            scopes=raw_scopes,
            aud=args.aud,
            description=args.description or f"Initial token for {args.client_id}",
            expires_in_days=args.expiry_days,
        )
        print("==================================================")
        print("TOKEN CREATED SUCCESSFULLY")
        print("==================================================")
        print(f"Client ID:      {args.client_id}")
        print(f"Token Hash:     {record['token_hash']}")
        print(f"Scopes:         {', '.join(record['scopes'])}")
        print(f"Audience:       {record['aud']}")
        print(f"Expires At:     {record['expires_at']}")
        print("--------------------------------------------------")
        print("NEW RAW TOKEN (Save immediately; not stored in plaintext):")
        print(raw_token)
        print("==================================================")
        return 0

    if args.revoke_client:
        count = tm.revoke_by_client_id(args.revoke_client, reason=args.reason)
        print(f"[SUCCESS] Revoked {count} active/grace tokens for client_id: {args.revoke_client}")
        return 0

    if args.revoke_hash:
        ok = tm.revoke_token(args.revoke_hash, reason=args.reason)
        if ok:
            print(f"[SUCCESS] Revoked token hash: {args.revoke_hash}")
            return 0
        print(f"[ERROR] Token hash not found: {args.revoke_hash}", file=sys.stderr)
        return 1

    if args.list:
        tokens = tm.list_tokens(client_id=args.client_id)
        print(f"Total tokens found: {len(tokens)}")
        for i, t in enumerate(tokens, 1):
            print(f"[{i}] Client: {t['client_id']} | Status: {t['status']} | Scopes: {t['scopes']} | Expires: {t['expires_at']}")
            print(f"    Hash: {t['token_hash']}")
            if t.get("grace_until"):
                print(f"    Grace Until: {t['grace_until']}")
            if t.get("revoked_at"):
                print(f"    Revoked At: {t['revoked_at']} (Reason: {t.get('revocation_reason')})")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
