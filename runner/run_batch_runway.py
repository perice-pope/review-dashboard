#!/usr/bin/env python3
"""
run_batch_runway.py — Runway Gen-4 References handler.

Pulls shots from production_queue where primary_tool='runway_gen4_references',
resolves character refs from Runway's asset library, submits ONE Gen-4
References call per shot (all characters in one scene — no compositing),
polls until done, saves the generated video to Google Drive via the Apps
Script webapp, writes result URL back to the DB, and marks review_pending.

Cloud-only — no local files. Matches the patterns already in run_batch.py:
    • runway://asset/{uuid}   for character PNGs (Runway asset library)
    • gdrive://{file_id}      for anything in Drive (not used here — Gen-4
                              doesn't ingest audio; hook is mux'd in Phase 5)
    • DRIVE_WEBAPP_URL        for saving generated videos to Drive

Usage:
    python3 run_batch_runway.py              # interactive
    python3 run_batch_runway.py --all        # process every ready row
    python3 run_batch_runway.py --auto       # non-interactive (cron)

Environment variables (all already in your .env):
    SUPABASE_URL, SUPABASE_KEY
    RUNWAY_API_KEY
    DRIVE_WEBAPP_URL
"""

import argparse
import json
import os
import ssl
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# macOS Python often lacks root certs. Prefer certifi's bundle when available.
try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CTX = ssl.create_default_context()


# ---------------------------------------------------------------------
# Config — mirrors run_batch.py conventions
# ---------------------------------------------------------------------
def _load_env(path: Path) -> dict:
    env = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env


_HERE = Path(__file__).parent.resolve()
_ENV = _load_env(_HERE / ".env")

SUPABASE_URL      = _ENV.get("SUPABASE_URL")      or os.environ.get("SUPABASE_URL")
SUPABASE_KEY      = _ENV.get("SUPABASE_KEY")      or os.environ.get("SUPABASE_KEY")
RUNWAY_API_KEY    = _ENV.get("RUNWAY_API_KEY")    or os.environ.get("RUNWAY_API_KEY")
DRIVE_WEBAPP_URL  = _ENV.get("DRIVE_WEBAPP_URL")  or os.environ.get("DRIVE_WEBAPP_URL", "")

RUNWAY_BASE       = "https://api.dev.runwayml.com/v1"
RUNWAY_VERSION    = "2024-11-06"
RUNWAY_MODEL      = "gen4.5"    # valid options (as of this run): gen3a_turbo,
                                # gen4.5, kling3.0_pro/_standard, klingO3_pro/_standard,
                                # seedance2, veo3, veo3.1, veo3.1_fast

MAX_ATTEMPTS      = 3
POLL_INTERVAL     = 10
POLL_TIMEOUT      = 60 * 8
GEN4_MAX_DURATION = 10    # Gen-4 Turbo supports 5 or 10 seconds max per call


missing = [k for k, v in [("SUPABASE_URL", SUPABASE_URL),
                          ("SUPABASE_KEY", SUPABASE_KEY),
                          ("RUNWAY_API_KEY", RUNWAY_API_KEY)] if not v]
if missing:
    sys.exit(f"Missing required env vars in .env: {', '.join(missing)}")


# ---------------------------------------------------------------------
# Minimal HTTP helper (no external deps)
# ---------------------------------------------------------------------
def http(url, method="GET", headers=None, data=None, raw_body=None, timeout=60):
    """Return (status_code, parsed_json_or_text)."""
    headers = dict(headers or {})
    if data is not None and raw_body is None:
        raw_body = json.dumps(data).encode("utf-8")
        headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, method=method, headers=headers, data=raw_body)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as resp:
            body = resp.read()
            status = resp.getcode()
    except urllib.error.HTTPError as e:
        body = e.read()
        status = e.code
    except Exception as e:
        return 0, {"error": str(e)}

    text = body.decode("utf-8", errors="replace")
    try:
        return status, json.loads(text)
    except ValueError:
        return status, text


# ---------------------------------------------------------------------
# Supabase (REST, matching run_batch.py)
# ---------------------------------------------------------------------
SB_HEADERS = {
    "apikey":        SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type":  "application/json",
    "Prefer":        "return=representation",
}


def fetch_ready_shots():
    q = urllib.parse.urlencode({
        "primary_tool": "eq.runway_gen4_references",
        "status":       "in.(queued,revision_needed)",
        "order":        "created_at.asc",
    })
    status, resp = http(
        f"{SUPABASE_URL}/rest/v1/production_queue?{q}",
        headers=SB_HEADERS,
    )
    if status != 200:
        sys.exit(f"Supabase fetch failed [{status}]: {resp}")
    return resp or []


def update_shot(db_id, **fields):
    status, resp = http(
        f"{SUPABASE_URL}/rest/v1/production_queue?id=eq.{db_id}",
        method="PATCH",
        headers=SB_HEADERS,
        data=fields,
    )
    if status >= 400:
        print(f"  ⚠  DB update failed [{status}]: {resp}")


def record_generation_run(shot, video_url, drive_filename, drive_folder_url, duration):
    """
    Insert one row into generation_runs so Review Dashboard.html renders the
    video. Runway Gen-4 produces ONE composite video per shot (not one per
    character), so we insert exactly one row, joining all character names with
    ' + ' to mirror the Hand Grab Momentum convention.
    """
    chars_raw = shot.get("characters_used") or ""
    chars = [c.strip() for c in chars_raw.split(",") if c.strip()]
    character_name = " + ".join(chars) if chars else "ensemble"
    payload = {
        "production_queue_id": shot["id"],
        "shot_name":           shot.get("shot_name"),
        "character_name":      character_name,
        "tool_used":           "runway",
        "fal_status":          "completed",
        "video_url":           video_url,
        "drive_filename":      drive_filename,
        "drive_folder":        drive_folder_url,
        "duration_seconds":    duration,
        "resolution":          "720p",
        "audio_source":        "silent (mux audio in CapCut)",
        "completed_at":        datetime.now(timezone.utc).isoformat(),
    }
    status, resp = http(
        f"{SUPABASE_URL}/rest/v1/generation_runs",
        method="POST",
        headers=SB_HEADERS,
        data=payload,
    )
    if status >= 400:
        print(f"  ⚠  generation_runs insert failed [{status}]: {resp}")


# ---------------------------------------------------------------------
# Runway asset resolution (same pattern as run_batch.py)
# ---------------------------------------------------------------------
_runway_hdr = {
    "Authorization":    f"Bearer {RUNWAY_API_KEY}",
    "X-Runway-Version": RUNWAY_VERSION,
    "Content-Type":     "application/json",
}


def resolve_runway_asset(ref: str) -> str:
    """
    runway://asset/{uuid} → public HTTPS URL hosted by Runway.
    Falls through to the ref itself if it's already an HTTPS URL.
    """
    if ref.startswith("http://") or ref.startswith("https://"):
        return ref
    if not ref.startswith("runway://asset/"):
        raise ValueError(f"Unsupported character ref: {ref}")

    asset_id = ref.replace("runway://asset/", "")
    status, resp = http(f"{RUNWAY_BASE}/assets/{asset_id}", headers=_runway_hdr)
    if status != 200:
        raise RuntimeError(f"Runway asset lookup failed [{status}]: {resp}")

    url = (resp.get("url") or resp.get("downloadUrl") or resp.get("download_url")
           or resp.get("previewUrl") or (resp.get("previewUrls", [None]) or [None])[0])
    if not url:
        raise RuntimeError(f"Asset found but no URL. Keys: {list(resp.keys())}")
    return url


# Character registry.
# Drive direct-image URLs (lh3.googleusercontent.com/d/FILE_ID) — returns raw PNG
# bytes for files in a publicly-shared Drive folder. Runway Gen-4 References
# fetches each URL directly. Swap the FILE_ID if you pick a different reference.
_DRIVE_IMG = "https://lh3.googleusercontent.com/d/{}=s2048"
CHARACTERS = {
    "Peter":  _DRIVE_IMG.format("1QEmdr63x-PtQfXI8KrhFp2U1akodiW_M"),
    "Marcus": _DRIVE_IMG.format("17wlhVnXclHswTqkUoBAIWL8lyMit-qH9"),
    "Julian": _DRIVE_IMG.format("1qaBCNVuPDejC-PR6s_xGSW8prA7pAMlw"),
    "Noah":   _DRIVE_IMG.format("12GiLteJSpiKZ9ReMGY1GnWl5IF5XOQeg"),
    "Maya":   _DRIVE_IMG.format("1MhfH14NUxrUH40ToepBcjZyzW6i9jPCK"),
}

import re

def extract_characters_from_prompt(prompt: str) -> list[str]:
    """
    Scan the prompt for @name tokens and return the matching character names
    from the CHARACTERS registry (case-insensitive match).

    Example: "@peter plays trumpet while @marcus nods" → ["Peter", "Marcus"]
    """
    tags = set(t.lower() for t in re.findall(r"@([A-Za-z]+)", prompt))
    return [name for name in CHARACTERS if name.lower() in tags]


def build_reference_images(shot: dict) -> list[dict]:
    """
    Build the Runway Gen-4 referenceImages array for a shot.

    Character resolution order:
      1. shot['characters_used'] — comma-separated names from DB
      2. @name tokens inside shot['runway_prompt']
      3. shot['character_refs'] — JSON array of runway:// URIs (positional,
         names inferred by index from CHARACTERS)
    """
    prompt = shot.get("runway_prompt") or shot.get("final_prompt") or ""

    # 1. Names from characters_used ("Peter, Marcus, Julian")
    names_raw = shot.get("characters_used") or ""
    names = [n.strip() for n in names_raw.split(",") if n.strip()]

    # 2. Fallback: extract @tags from prompt
    if not names:
        names = extract_characters_from_prompt(prompt)

    if not names:
        raise ValueError("No characters found on shot — populate characters_used or add @name tags to runway_prompt")

    refs = []
    for name in names:
        asset_ref = CHARACTERS.get(name)
        if not asset_ref:
            raise ValueError(f"Unknown character '{name}' — add to CHARACTERS registry")
        url = resolve_runway_asset(asset_ref)
        refs.append({"tag": name.lower(), "uri": url})
    return refs


# ---------------------------------------------------------------------
# Runway Gen-4 submission + polling
# ---------------------------------------------------------------------
def submit_gen4(prompt, references, duration=10, ratio="720:1280"):
    body = {
        "model":           RUNWAY_MODEL,
        "promptText":      prompt,
        "referenceImages": references,
        "duration":        duration,
        "ratio":           ratio,
    }
    status, resp = http(
        f"{RUNWAY_BASE}/text_to_video",
        method="POST", headers=_runway_hdr, data=body, timeout=60,
    )
    if status >= 400:
        raise RuntimeError(f"Runway submit failed [{status}]: {resp}")
    return resp["id"]


def poll_gen4(task_id):
    started = time.time()
    while True:
        status, resp = http(
            f"{RUNWAY_BASE}/tasks/{task_id}", headers=_runway_hdr, timeout=30,
        )
        if status != 200:
            raise RuntimeError(f"Poll failed [{status}]: {resp}")
        state = resp.get("status")
        if state == "SUCCEEDED":
            return resp
        if state in ("FAILED", "CANCELLED"):
            raise RuntimeError(f"Task {state}: {resp}")
        if time.time() - started > POLL_TIMEOUT:
            raise TimeoutError(f"Task {task_id} stuck in {state} after {POLL_TIMEOUT}s")
        time.sleep(POLL_INTERVAL)


# ---------------------------------------------------------------------
# Save to Drive via Apps Script webapp (same as run_batch.py)
# ---------------------------------------------------------------------
def save_to_drive(folder_name, filename, video_url):
    if not DRIVE_WEBAPP_URL:
        print("    ⚠  DRIVE_WEBAPP_URL not set — skipping Drive save")
        return None
    payload = {"folderName": folder_name, "videos": [[filename, video_url]]}
    status, resp = http(
        DRIVE_WEBAPP_URL, method="POST",
        headers={"Content-Type": "application/json"},
        data=payload, timeout=300,
    )
    if status == 200:
        return resp.get("folderUrl", "")
    print(f"    ⚠  Drive save failed [{status}]: {str(resp)[:200]}")
    return None


# ---------------------------------------------------------------------
# Process one shot
# ---------------------------------------------------------------------
def process_shot(shot):
    db_id = shot["id"]
    name  = shot.get("shot_name", db_id)
    song  = shot.get("song_title", "Unknown Song")

    print(f"\n[{name}] start — song={song}")
    update_shot(db_id, status="generating")

    try:
        refs = build_reference_images(shot)
        print(f"  refs: {[r['tag'] for r in refs]}")
    except Exception as e:
        update_shot(db_id, status="revision_needed",
                    review_notes=f"Ref resolution failed: {str(e)[:400]}")
        print(f"  FAILED during ref resolution: {e}")
        return

    # Map aspect_ratio "9:16" → Runway ratio "720:1280"
    ar_raw = shot.get("aspect_ratio", "9:16")
    ratio = {"9:16": "720:1280", "16:9": "1280:720"}.get(ar_raw, ar_raw)

    # Cap duration at Gen-4 Turbo limit
    requested = shot.get("duration_seconds") or 10
    duration = min(requested, GEN4_MAX_DURATION)
    if duration < requested:
        print(f"  ⚠  duration capped: {requested}s → {duration}s (Gen-4 Turbo limit)")
    if duration not in (5, 10):
        duration = 10  # Gen-4 Turbo only accepts 5 or 10

    prompt = shot.get("runway_prompt") or shot.get("final_prompt") or ""
    if not prompt:
        update_shot(db_id, status="failed", review_notes="runway_prompt empty")
        print("  FAILED — runway_prompt is empty")
        return

    for attempt in range(1, MAX_ATTEMPTS + 1):
        print(f"  attempt {attempt}/{MAX_ATTEMPTS} — submitting {duration}s @ {ratio} …")
        try:
            task_id = submit_gen4(
                prompt     = prompt,
                references = refs,
                duration   = duration,
                ratio      = ratio,
            )
            print(f"  task {task_id} — polling")
            result    = poll_gen4(task_id)
            video_url = result["output"][0] if isinstance(result.get("output"), list) else result.get("output")

            filename     = f"{song.replace(' ', '')}_{name.replace(' ', '')}_gen4_v{attempt}.mp4"
            drive_folder = f"{song} - Generated Shots"
            folder_url   = save_to_drive(drive_folder, filename, video_url)

            update_shot(
                db_id,
                status             = "review_pending",
                asset_url          = video_url,
                drive_folder_url   = folder_url or None,
                review_notes       = f"Runway Gen-4 References, attempt {attempt}, task {task_id}",
                reviewer_feedback  = None,
            )
            record_generation_run(shot, video_url, filename, folder_url, duration)
            print(f"  DONE → {video_url}")
            return

        except Exception as e:
            print(f"  attempt {attempt} failed: {e}")
            if attempt == MAX_ATTEMPTS:
                update_shot(db_id, status="revision_needed",
                            review_notes=f"Runway Gen-4 failed after {MAX_ATTEMPTS} attempts: {str(e)[:200]}")
                print("  FAILED — all attempts exhausted, shot left at revision_needed")
                return
            time.sleep(5)


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--all",  action="store_true", help="Process every ready shot")
    ap.add_argument("--auto", action="store_true", help="Non-interactive (implies --all)")
    args = ap.parse_args()

    shots = fetch_ready_shots()
    if not shots:
        print("No shots ready for Runway Gen-4 generation.")
        return

    print(f"\n{len(shots)} shot(s) ready:\n")
    for i, s in enumerate(shots, 1):
        chars_raw = s.get("characters_used") or ""
        chars = [c.strip() for c in chars_raw.split(",") if c.strip()]
        print(f"  {i}. {s.get('shot_name', '?'):<32} song={s.get('song_title', '?'):<22} "
              f"dur={s.get('duration_seconds')}s  chars={len(chars)} ({chars_raw})")

    if args.all or args.auto:
        selected = shots
    else:
        choice = input("\nRun which? (a=all, 1,2,3 = specific, q=quit): ").strip().lower()
        if choice == "q":
            return
        if choice == "a":
            selected = shots
        else:
            idxs = [int(x) - 1 for x in choice.split(",") if x.strip().isdigit()]
            selected = [shots[i] for i in idxs if 0 <= i < len(shots)]

    for shot in selected:
        process_shot(shot)

    print("\nBatch complete.")


if __name__ == "__main__":
    main()
