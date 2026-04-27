#!/usr/bin/env python3
"""
clean_prompts.py — one-off (or rerunnable) sweep that applies Runway Gen-4
prompting rules to existing production_queue.runway_prompt fields.

For every shot with primary_tool='runway_gen4_references', this asks Claude to
rewrite the runway_prompt: strip identity descriptors that violate Rule 1
(references handle identity), keep action/environment/camera/mood. The prior
prompt is preserved in previous_runway_prompt for rollback.

Reads ANTHROPIC_API_KEY, SUPABASE_URL, SUPABASE_KEY from .env in the same
directory or from process env. Idempotent — running it twice on already-clean
prompts is a no-op.

Usage:
    python3 clean_prompts.py            # interactive: shows diff, asks per-shot
    python3 clean_prompts.py --auto     # non-interactive, applies all
    python3 clean_prompts.py --dry-run  # shows diffs without writing
"""

import argparse
import json
import os
import ssl
import sys
import urllib.parse
import urllib.request
from pathlib import Path

try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CTX = ssl.create_default_context()


def _load_env(path: Path) -> dict:
    env: dict = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


_ENV = _load_env(Path(__file__).parent / ".env")
# Also try the parent project dir's .env (where the user keeps secrets)
_ENV.update({k: v for k, v in _load_env(Path(__file__).resolve().parents[3] / ".env").items() if k not in _ENV})

SUPABASE_URL      = _ENV.get("SUPABASE_URL")      or os.environ.get("SUPABASE_URL")
SUPABASE_KEY      = _ENV.get("SUPABASE_KEY")      or os.environ.get("SUPABASE_KEY")
ANTHROPIC_API_KEY = _ENV.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")

missing = [k for k, v in [("SUPABASE_URL", SUPABASE_URL),
                          ("SUPABASE_KEY", SUPABASE_KEY),
                          ("ANTHROPIC_API_KEY", ANTHROPIC_API_KEY)] if not v]
if missing:
    sys.exit(f"Missing env vars: {', '.join(missing)}")


SB_HEADERS = {
    "apikey":        SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type":  "application/json",
    "Prefer":        "return=representation",
}


SYSTEM_PROMPT = """You are a prompt engineer for the Runway Gen-4 References video model. Your job is to clean a shot's runway_prompt so it follows Runway's official prompting rules.

RUNWAY GEN-4 PROMPTING RULES:

1. REFERENCES HANDLE IDENTITY. Each @-tagged character has a reference image that defines face, hair, build, age, clothing, accessories. The PROMPT MUST NOT redescribe any of these. Forbidden: hair color/style, age, build, race, clothing item, clothing color, accessories, facial features, jewelry. STRIP all of these from the prompt.

2. PROMPTS HANDLE ACTION + ENVIRONMENT + CAMERA + MOOD only. Keep what the characters DO (verbs, motion), WHERE they are (location, lighting, atmosphere, weather), how the CAMERA moves (push, pull, pan, framing), and what the scene FEELS like (mood, audio cues that drive action).

3. PRESERVE EXPLICIT NEGATIVE-PROMPT INSTRUCTIONS. Phrases like "no breath vapor", "no condensation from mouths", "no eye contact", "NOT choreography", "NOT 3D", "do not show X" are deliberate constraints — usually added in response to prior reviewer feedback. KEEP them intact even if they make the prompt longer. Negative guidance is NOT bloat.

4. KEEP IT SHORT (within reason). Cut redundancy and decorative description, but never at the cost of Rule 3 caveats.

5. CHARACTERS ARE @-TAGGED. Format: @Name. The reference image supplies their look — just say what @Name does, never describe them.

6. PRESERVE the global visual-style line (e.g. "Roommates visual style: ...") since it's rendering style not character identity. Trim it only if it bloats the prompt.

7. If the prompt is ALREADY clean — no identity descriptors to strip, already concise — return it unchanged.

Output via the clean_prompt tool. The rationale should briefly note (a) what you stripped, and (b) "no changes needed" if the prompt was already clean."""


CLEAN_TOOL = {
    "name": "clean_prompt",
    "description": "Submit the cleaned runway_prompt for the shot.",
    "input_schema": {
        "type": "object",
        "properties": {
            "runway_prompt": {
                "type": "string",
                "description": "The cleaned prompt. May equal the original if no changes were needed.",
            },
            "rationale": {
                "type": "string",
                "description": "1–2 sentences describing what you stripped, or 'no changes needed'.",
            },
        },
        "required": ["runway_prompt", "rationale"],
    },
}


def http(url, method="GET", headers=None, data=None, timeout=60):
    headers = dict(headers or {})
    raw = json.dumps(data).encode("utf-8") if data is not None else None
    if raw is not None:
        headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, method=method, headers=headers, data=raw)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return resp.getcode(), json.loads(body) if body else None
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(body)
        except ValueError:
            return e.code, body


def fetch_runway_shots():
    q = urllib.parse.urlencode({
        "primary_tool": "eq.runway_gen4_references",
        "select":       "id,shot_name,characters_used,runway_prompt",
        "order":        "shot_name.asc",
    })
    status, resp = http(f"{SUPABASE_URL}/rest/v1/production_queue?{q}", headers=SB_HEADERS)
    if status != 200:
        sys.exit(f"Supabase fetch failed [{status}]: {resp}")
    return [r for r in resp if r.get("runway_prompt")]


def update_shot(shot_id: str, new_prompt: str, prev_prompt: str):
    payload = {
        "runway_prompt":          new_prompt,
        "previous_runway_prompt": prev_prompt,
    }
    status, resp = http(
        f"{SUPABASE_URL}/rest/v1/production_queue?id=eq.{shot_id}",
        method="PATCH", headers=SB_HEADERS, data=payload,
    )
    if status >= 400:
        print(f"    ⚠  update failed [{status}]: {resp}")
        return False
    return True


def call_claude(shot: dict) -> dict:
    user_msg = (
        f"SHOT NAME: {shot.get('shot_name', '')}\n"
        f"characters_used: {shot.get('characters_used', '')}\n"
        f"\nCURRENT runway_prompt:\n{shot.get('runway_prompt', '')}\n"
        f"\nApply the rules. Return the cleaned prompt."
    )
    status, resp = http(
        "https://api.anthropic.com/v1/messages",
        method="POST",
        headers={
            "x-api-key":         ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
        },
        data={
            "model":       "claude-sonnet-4-6",
            "max_tokens":  1024,
            "system":      SYSTEM_PROMPT,
            "tools":       [CLEAN_TOOL],
            "tool_choice": {"type": "tool", "name": "clean_prompt"},
            "messages":    [{"role": "user", "content": user_msg}],
        },
        timeout=120,
    )
    if status != 200:
        raise RuntimeError(f"Anthropic API {status}: {resp}")
    block = next((b for b in resp.get("content", []) if b.get("type") == "tool_use"), None)
    if not block:
        raise RuntimeError(f"No tool_use block: {resp}")
    return block["input"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--auto",    action="store_true", help="Apply without per-shot confirmation")
    ap.add_argument("--dry-run", action="store_true", help="Show diffs without writing to DB")
    args = ap.parse_args()

    shots = fetch_runway_shots()
    print(f"\nFound {len(shots)} runway shots with prompts.\n")

    changed = 0
    skipped = 0
    for i, shot in enumerate(shots, 1):
        print(f"[{i}/{len(shots)}] {shot['shot_name']}")
        try:
            result = call_claude(shot)
        except Exception as e:
            print(f"    ⚠  Claude call failed: {e}")
            continue

        new_prompt = result["runway_prompt"].strip()
        rationale  = result.get("rationale", "")

        if new_prompt == shot["runway_prompt"].strip():
            print(f"    ✓ already clean — {rationale}")
            skipped += 1
            continue

        old_len = len(shot["runway_prompt"])
        new_len = len(new_prompt)
        print(f"    → rationale: {rationale}")
        print(f"    → length: {old_len} → {new_len} chars")
        print(f"    --- BEFORE ---\n    {shot['runway_prompt']}")
        print(f"    --- AFTER  ---\n    {new_prompt}")

        if args.dry_run:
            print("    [dry-run] not writing")
            continue

        if not args.auto:
            ans = input("    Apply this change? [y/N/q]: ").strip().lower()
            if ans == "q":
                print("Stopping.")
                break
            if ans != "y":
                print("    Skipped.")
                continue

        if update_shot(shot["id"], new_prompt, shot["runway_prompt"]):
            print("    ✓ applied")
            changed += 1

    print(f"\nDone. Cleaned: {changed}, already clean: {skipped}.")


if __name__ == "__main__":
    main()
