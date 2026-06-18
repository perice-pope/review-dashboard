#!/usr/bin/env python3
"""
_common.py — shared helpers for the Character Pipeline scripts.

Pure-stdlib helpers shared by train_lora.py, generate_stills.py, animate.py:
key handling (env-only, never printed), the paid-action approval gate, status
printing for async polling, and a robust file downloader for the
Replicate -> Runway handoff.

HARD RULES enforced here:
  - API keys are read ONLY from environment variables.
  - Keys are NEVER printed, logged, written to disk, or echoed in errors.
  - No paid API call happens without explicit approval (see require_approval()).
"""
from __future__ import annotations

import os
import sys
import ssl
import time
import base64
import mimetypes
import urllib.request
from pathlib import Path

# Replicate's edge rejects the default python-urllib User-Agent with a 403.
# Any non-default UA gets through. Used for all raw downloads.
_UA = "roommates-character-pipeline/1.0"
_SSL_CTX = ssl.create_default_context()


# ─────────────────────────────────────────────────────────────────────────────
#  Key handling — env vars only, never printed
# ─────────────────────────────────────────────────────────────────────────────
def replicate_token() -> str:
    """Return the user's Replicate token from env, or exit with a pointer.

    NEVER prints the token. The only thing surfaced is the env var NAME.
    """
    tok = os.environ.get("REPLICATE_API_TOKEN", "").strip()
    if not tok:
        sys.exit(
            "REPLICATE_API_TOKEN is not set.\n"
            "  Set it locally before running:  export REPLICATE_API_TOKEN=...\n"
            "  Get a token at https://replicate.com/account/api-tokens\n"
            "  (This skill never stores or transmits your key anywhere but Replicate.)"
        )
    return tok


def runway_key() -> str:
    """Return the user's Runway key from env, or exit with a pointer.

    Accepts RUNWAY_API_KEY (this skill's documented name) and falls back to
    RUNWAYML_API_SECRET (the official SDK's default name) so either works.
    NEVER prints the key.
    """
    key = (
        os.environ.get("RUNWAY_API_KEY", "").strip()
        or os.environ.get("RUNWAYML_API_SECRET", "").strip()
    )
    if not key:
        sys.exit(
            "RUNWAY_API_KEY is not set.\n"
            "  Set it locally before running:  export RUNWAY_API_KEY=...\n"
            "  Get a key in the Runway developer portal: https://dev.runwayml.com\n"
            "  (This skill never stores or transmits your key anywhere but Runway.)"
        )
    return key


def is_auth_error(err: Exception) -> bool:
    """Best-effort detection of an auth/permission failure so callers can point
    the user at their env var instead of dumping a stack trace."""
    msg = str(err).lower()
    return any(
        s in msg
        for s in ("401", "403", "unauthorized", "authentication", "invalid token",
                  "invalid api", "permission", "forbidden")
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Approval gate — no paid call without explicit consent
# ─────────────────────────────────────────────────────────────────────────────
def require_approval(action: str, est_cost: str, *, assume_yes: bool) -> None:
    """Gate every paid API call. Each call spends the BUYER's money on their
    own Replicate/Runway account, so nothing runs without explicit approval.

    - If `assume_yes` is True (the --yes flag, set only after the user approved
      in the Claude conversation), proceed.
    - Otherwise, if attached to a terminal, prompt for a typed 'yes'.
    - Otherwise (non-interactive, no approval), refuse and explain how to approve.
    """
    banner = (
        "\n────────────────────────────────────────────────────────\n"
        f"  PAID ACTION — runs on YOUR account, costs YOUR money\n"
        f"  Action:         {action}\n"
        f"  Est. cost:      {est_cost}\n"
        "────────────────────────────────────────────────────────"
    )
    print(banner)
    if assume_yes:
        print("  Approved (--yes). Proceeding.\n")
        return
    if sys.stdin and sys.stdin.isatty():
        resp = input("  Type 'yes' to approve this charge: ").strip().lower()
        if resp in ("y", "yes"):
            print()
            return
        sys.exit("  Not approved — nothing was run, nothing was charged.")
    sys.exit(
        "  Refusing to run a paid generation without approval.\n"
        "  Re-run with --yes ONLY after the buyer has explicitly approved this charge."
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Async status surfacing
# ─────────────────────────────────────────────────────────────────────────────
def status_line(label: str, state: str, started: float, extra: str = "") -> None:
    """Print a single-line, non-spammy status update for a polling loop."""
    mins, secs = divmod(int(time.time() - started), 60)
    tail = f"  {extra}" if extra else ""
    print(f"  [{label}] {state:<12} {mins:02d}:{secs:02d} elapsed{tail}", flush=True)


# ─────────────────────────────────────────────────────────────────────────────
#  File I/O — the Replicate -> Runway handoff lives here
# ─────────────────────────────────────────────────────────────────────────────
def download(url: str, dest: str | Path, *, timeout: int = 120) -> Path:
    """Download a URL to a local path. Used to pull trained-LoRA stills off
    Replicate (delivery URLs are short-lived, ~1h) before they expire.

    Returns the local Path. Raises on HTTP error or an implausibly small file.
    """
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as r:
        if r.status != 200:
            raise RuntimeError(f"Download failed [{r.status}] for {url[:80]}…")
        data = r.read()
    if len(data) < 512:
        raise RuntimeError(
            f"Downloaded file is suspiciously small ({len(data)} bytes) — "
            f"the source URL may have expired: {url[:80]}…"
        )
    dest.write_bytes(data)
    return dest


def to_data_uri(image_path: str | Path) -> str:
    """Encode a local image as a base64 data URI.

    This is the safe form for the Replicate -> Runway handoff: rather than
    handing Runway a short-lived Replicate URL that may expire or be refused,
    we download the still locally (already done in Stage 2) and feed Runway the
    bytes inline. Runway's image endpoints accept `data:image/...;base64,` URIs.
    """
    p = Path(image_path)
    if not p.is_file():
        raise FileNotFoundError(f"Still not found for handoff: {p}")
    mime, _ = mimetypes.guess_type(str(p))
    mime = mime or "image/png"
    b64 = base64.b64encode(p.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


def prompt_image_for_runway(image: str | Path) -> str:
    """Resolve whatever the user points at into something Runway will accept as
    promptImage. A local file becomes a base64 data URI (the robust handoff);
    an http(s) URL passes through unchanged.
    """
    s = str(image).strip()
    if s.startswith("http://") or s.startswith("https://") or s.startswith("data:image/"):
        return s
    return to_data_uri(s)
