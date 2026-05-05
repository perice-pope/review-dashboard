#!/usr/bin/env python3
"""
run_batch_runway.py — Runway Gen-4 References handler (two-stage pipeline).

Pulls shots from production_queue where primary_tool='runway_gen4_references'
and runs them through Runway as a two-stage call:

    Stage 1 — Keyframe:
        POST /v1/text_to_image (model=gen4_image)
        + referenceImages (≤3, characters first, then scene if room)
        → still PNG that locks in character likenesses + setting

    Stage 2 — Animation:
        POST /v1/image_to_video (model=gen4.5)
        + promptImage = the Stage 1 PNG
        + promptText  = the same shot prompt (drives motion)
        → final MP4

Why two stages: Runway's referenceImages parameter only exists on the image
endpoints. text_to_video silently drops the field. Single-stage with refs
never worked — it was producing pure-text-prompt video that ignored the
character/setting library.

The runner saves the final MP4 to Drive via the Apps Script webapp and
records a row in generation_runs.

Environment variables (.env in this directory or process env):
    SUPABASE_URL, SUPABASE_KEY
    RUNWAY_API_KEY
    DRIVE_WEBAPP_URL  (optional; if unset, video URL is recorded but not
                       copied to Drive)

Usage:
    python3 run_batch_runway.py              # interactive
    python3 run_batch_runway.py --all        # process every ready row
    python3 run_batch_runway.py --auto       # non-interactive (cron)
"""

import argparse
import json
import os
import re
import ssl
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Local registry — single source of truth for character/scene images and LoRAs.
sys.path.insert(0, str(Path(__file__).parent.resolve()))
from assets import (  # noqa: E402
    CHARACTERS, SCENES, CHARACTER_LORAS, INSERT_MODEL,
    lookup_character, lookup_scene, lookup_lora, all_loras_ready,
)

try:
    import certifi
    _SSL_CTX = ssl.create_default_context(cafile=certifi.where())
except ImportError:
    _SSL_CTX = ssl.create_default_context()


# ─────────────────────────────────────────────────────────────────────────────
#  Config
# ─────────────────────────────────────────────────────────────────────────────
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


_HERE = Path(__file__).parent.resolve()
_ENV = _load_env(_HERE / ".env")
# Also try the parent project dir's .env (where the user keeps secrets)
for parent_env in (_HERE.parents[2] / ".env", _HERE.parents[3] / ".env"):
    _ENV.update({k: v for k, v in _load_env(parent_env).items() if k not in _ENV})

SUPABASE_URL        = _ENV.get("SUPABASE_URL")        or os.environ.get("SUPABASE_URL")
SUPABASE_KEY        = _ENV.get("SUPABASE_KEY")        or os.environ.get("SUPABASE_KEY")
RUNWAY_API_KEY      = _ENV.get("RUNWAY_API_KEY")      or os.environ.get("RUNWAY_API_KEY")
DRIVE_WEBAPP_URL    = _ENV.get("DRIVE_WEBAPP_URL")    or os.environ.get("DRIVE_WEBAPP_URL", "")
REPLICATE_API_TOKEN = _ENV.get("REPLICATE_API_TOKEN") or os.environ.get("REPLICATE_API_TOKEN", "")

RUNWAY_BASE    = "https://api.dev.runwayml.com/v1"
RUNWAY_VERSION = "2024-11-06"

REPLICATE_BASE = "https://api.replicate.com/v1"

# Legacy text_to_image path (kept for shots without LoRAs available)
KEYFRAME_MODEL = "gen4_image"

# Default animation model — Seedance 2. Per-shot override via production_queue.animation_model
DEFAULT_ANIMATION_MODEL = "seedance2"

REF_CAP        = 3
MAX_ATTEMPTS   = 3
POLL_INTERVAL  = 10
POLL_TIMEOUT   = 60 * 8
VIDEO_DURATION = 10

missing = [k for k, v in [("SUPABASE_URL", SUPABASE_URL),
                          ("SUPABASE_KEY", SUPABASE_KEY),
                          ("RUNWAY_API_KEY", RUNWAY_API_KEY)] if not v]
if missing:
    sys.exit(f"Missing required env vars: {', '.join(missing)}")


# ─────────────────────────────────────────────────────────────────────────────
#  HTTP helper (no external deps)
# ─────────────────────────────────────────────────────────────────────────────
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


# ─────────────────────────────────────────────────────────────────────────────
#  Supabase
# ─────────────────────────────────────────────────────────────────────────────
SB_HEADERS = {
    "apikey":        SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type":  "application/json",
    "Prefer":        "return=representation",
}


STUCK_GENERATING_MINUTES = 15  # how long a 'generating' shot must idle before we
                               # treat it as orphaned (cancelled/crashed previous run)


def recover_stuck_shots():
    """
    Reset shots stuck in any transient runner state for > STUCK_GENERATING_MINUTES
    back to 'queued' so they get retried. Catches cancelled/crashed runners.
    Transient states: 'generating' (legacy), 'still_pending', 'animating'.
    """
    cutoff = (datetime.now(timezone.utc)
              - timedelta(minutes=STUCK_GENERATING_MINUTES)).isoformat()
    q = urllib.parse.urlencode({
        "primary_tool": "eq.runway_gen4_references",
        "status":       "in.(generating,still_pending,animating)",
        "updated_at":   f"lt.{cutoff}",
        "select":       "id,shot_name,status,updated_at",
    })
    status, resp = http(f"{SUPABASE_URL}/rest/v1/production_queue?{q}", headers=SB_HEADERS)
    if status != 200 or not isinstance(resp, list):
        return
    for shot in resp:
        print(f"  ⏪  reviving stuck shot {shot.get('shot_name')} "
              f"({shot.get('status')} since {shot.get('updated_at')})")
        # If they were animating, keyframe was set → revision_needed retries Stage 2.
        # Otherwise → queued retries Stage 1.
        revive_to = "revision_needed" if shot.get("status") == "animating" else "queued"
        update_shot(shot["id"], status=revive_to,
                    review_notes="Auto-revived: previous runner did not complete")


def fetch_ready_shots():
    recover_stuck_shots()
    # Pick up shots in any state where the runner has work to do:
    #   queued          → fresh shot, generate still via Replicate (or fall back)
    #   revision_needed → user clicked Animate or revised; runner picks next stage
    q = urllib.parse.urlencode({
        "primary_tool": "eq.runway_gen4_references",
        "status":       "in.(queued,revision_needed)",
        "order":        "created_at.asc",
    })
    status, resp = http(f"{SUPABASE_URL}/rest/v1/production_queue?{q}", headers=SB_HEADERS)
    if status != 200:
        sys.exit(f"Supabase fetch failed [{status}]: {resp}")
    return resp or []


def update_shot(db_id, **fields):
    status, resp = http(
        f"{SUPABASE_URL}/rest/v1/production_queue?id=eq.{db_id}",
        method="PATCH", headers=SB_HEADERS, data=fields,
    )
    if status >= 400:
        print(f"  ⚠  DB update failed [{status}]: {resp}")


def count_existing_runs(shot_id: str) -> int:
    status, resp = http(
        f"{SUPABASE_URL}/rest/v1/generation_runs?production_queue_id=eq.{shot_id}&select=id",
        headers={**SB_HEADERS, "Prefer": "count=exact"},
    )
    if status != 200 or not isinstance(resp, list):
        return 0
    return len(resp)


def record_generation_run(shot, video_url, drive_filename, drive_folder_url, duration, keyframe_url):
    """One row per shot run; keyframe_url goes into error_message-adjacent metadata."""
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
    # keyframe_url is debug-useful but generation_runs has no dedicated column
    # for it. Stash it in fal_request_id so it shows up in the dashboard's
    # raw run record without requiring a migration.
    if keyframe_url:
        payload["fal_request_id"] = f"keyframe={keyframe_url}"
    status, resp = http(
        f"{SUPABASE_URL}/rest/v1/generation_runs",
        method="POST", headers=SB_HEADERS, data=payload,
    )
    if status >= 400:
        print(f"  ⚠  generation_runs insert failed [{status}]: {resp}")


# ─────────────────────────────────────────────────────────────────────────────
#  Runway asset resolution
# ─────────────────────────────────────────────────────────────────────────────
_runway_hdr = {
    "Authorization":    f"Bearer {RUNWAY_API_KEY}",
    "X-Runway-Version": RUNWAY_VERSION,
    "Content-Type":     "application/json",
}


def resolve_uri(ref: str) -> str:
    """
    Pass-through for the three URI forms Runway accepts in referenceImages.uri:
      • https://...
      • runway://upload/<id>  (from POST /v1/uploads)
      • data:image/...        (base64 data URI)

    The legacy runway://asset/<uuid> form (from older Runway asset library) is
    no longer accepted — fail loudly with a fix hint instead of silently using
    a deprecated endpoint.
    """
    if not ref:
        raise ValueError("Empty reference URI")
    if ref.startswith("http://") or ref.startswith("https://"):
        return ref
    if ref.startswith("runway://upload/") or ref.startswith("data:image/"):
        return ref
    if ref.startswith("runway://asset/"):
        raise ValueError(
            f"Legacy runway://asset/ URIs are no longer supported by referenceImages "
            f"({ref}). Re-host the image on Drive (use drive('<file_id>') in assets.py) "
            f"or upload via POST /v1/uploads and use runway://upload/<id>."
        )
    raise ValueError(f"Unsupported ref scheme: {ref}")


_DRIVE_ID_PATTERNS = [
    re.compile(r"drive\.google\.com/file/d/([A-Za-z0-9_-]{20,})"),
    re.compile(r"drive\.google\.com/open\?id=([A-Za-z0-9_-]{20,})"),
    re.compile(r"lh3\.googleusercontent\.com/d/([A-Za-z0-9_-]{20,})"),
]


def resolve_keyframe_uri(raw: str) -> str:
    """
    Normalize whatever the dashboard wrote into keyframe_image_url to a URI
    image_to_video can ingest as promptImage.

    Accepts:
      • Bare Drive file ID (20+ char alphanumeric+-_ string)
      • https://drive.google.com/file/d/<ID>/view  (and /open?id=)
      • https://lh3.googleusercontent.com/d/<ID>=...
      • Any other https:// URL → pass through
      • runway://upload/<id> → pass through
      • data:image/...       → pass through
    """
    if not raw:
        raise ValueError("Empty keyframe_image_url")
    s = raw.strip()
    # Pass-throughs Runway already accepts
    if s.startswith("runway://upload/") or s.startswith("data:image/"):
        return s
    # Match a Drive URL → extract file ID
    for pat in _DRIVE_ID_PATTERNS:
        m = pat.search(s)
        if m:
            return f"https://lh3.googleusercontent.com/d/{m.group(1)}=s2048"
    # Already an HTTPS URL we don't recognize as Drive → pass through
    if s.startswith("http://") or s.startswith("https://"):
        return s
    # Bare-looking Drive file ID
    if re.fullmatch(r"[A-Za-z0-9_-]{20,}", s):
        return f"https://lh3.googleusercontent.com/d/{s}=s2048"
    raise ValueError(f"Unsupported keyframe_image_url shape: {s[:80]}")


def extract_at_tags(prompt: str) -> list[str]:
    """All @tag tokens from a prompt, preserving order, deduped, lowercased."""
    seen, out = set(), []
    for tag in re.findall(r"@([A-Za-z][A-Za-z0-9_]*)", prompt or ""):
        low = tag.lower()
        if low not in seen:
            seen.add(low)
            out.append(low)
    return out


def build_reference_images(shot: dict) -> tuple[list[dict], list[str]]:
    """
    Build the referenceImages array (≤3) for the keyframe stage.

    Order of preference:
        1. Each name in characters_used (CSV)
        2. The scene_ref slug (one entry, only if room remains)

    Returns (refs, warnings). Refs use lowercase tags so the prompt's @Name
    matches case-insensitively (Runway is documented as case-sensitive on tags
    in some places; we normalize the prompt at submit time too).
    """
    warnings: list[str] = []

    names_raw = (shot.get("characters_used") or "").strip()
    names = [n.strip() for n in names_raw.split(",") if n.strip()] if names_raw else []
    if not names:
        # Fallback: pull @tags from the prompt and match against CHARACTERS
        prompt = shot.get("runway_prompt") or shot.get("final_prompt") or ""
        for tag in extract_at_tags(prompt):
            for char in CHARACTERS:
                if char.lower() == tag:
                    names.append(char)
                    break

    if not names:
        raise ValueError(
            "No characters resolvable from characters_used or @tags. "
            "Populate characters_used or add @Name tokens to runway_prompt."
        )

    refs: list[dict] = []
    for name in names:
        uri = lookup_character(name)
        if not uri:
            raise ValueError(f"Unknown character {name!r} — add it to runner/assets.py")
        refs.append({"tag": name.lower(), "uri": resolve_uri(uri)})

    if len(refs) > REF_CAP:
        dropped = [r["tag"] for r in refs[REF_CAP:]]
        warnings.append(f"capped at {REF_CAP} refs; dropped: {', '.join(dropped)}")
        refs = refs[:REF_CAP]

    # Scene ref — slot it in if there's room
    scene_tag = (shot.get("scene_ref") or "").strip()
    if scene_tag:
        scene_uri = lookup_scene(scene_tag)
        if not scene_uri:
            warnings.append(f"scene_ref {scene_tag!r} not found in SCENES — skipping")
        elif len(refs) < REF_CAP:
            refs.append({"tag": scene_tag.lower(), "uri": resolve_uri(scene_uri)})
        else:
            warnings.append(f"no room for scene_ref {scene_tag!r} (already at {REF_CAP} chars)")

    return refs, warnings


def normalize_prompt_tags(prompt: str, refs: list[dict]) -> str:
    """
    Make every @Name in the prompt lowercase to match the lowercase tags we
    send. Runway is case-sensitive in places; this avoids the silent-mismatch
    failure mode where @Peter doesn't bind to ref tag "peter".
    """
    if not prompt:
        return prompt
    valid = {r["tag"] for r in refs}

    def repl(m: re.Match) -> str:
        low = m.group(1).lower()
        return f"@{low}" if low in valid else m.group(0)

    return re.sub(r"@([A-Za-z][A-Za-z0-9_]*)", repl, prompt)


def validate_prompt_against_refs(prompt: str, refs: list[dict]) -> list[str]:
    """Warn if any ref tag isn't actually used in the prompt as @tag."""
    used = set(extract_at_tags(prompt))
    return [f"ref tag @{r['tag']} not referenced in prompt — image won't bind"
            for r in refs if r["tag"] not in used]


# ─────────────────────────────────────────────────────────────────────────────
#  Stage 1 — keyframe via text_to_image
# ─────────────────────────────────────────────────────────────────────────────
def submit_keyframe(prompt: str, refs: list[dict], ratio: str = "720:1280") -> str:
    body = {
        "model":           KEYFRAME_MODEL,
        "promptText":      prompt,
        "referenceImages": refs,
        "ratio":           ratio,
    }
    status, resp = http(
        f"{RUNWAY_BASE}/text_to_image",
        method="POST", headers=_runway_hdr, data=body, timeout=60,
    )
    if status >= 400:
        raise RuntimeError(f"Runway text_to_image failed [{status}]: {resp}")
    return resp["id"]


def poll_task(task_id: str) -> dict:
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
            raise RuntimeError(f"Task {state}: {resp.get('failure') or resp}")
        if time.time() - started > POLL_TIMEOUT:
            raise TimeoutError(f"Task {task_id} stuck in {state} after {POLL_TIMEOUT}s")
        time.sleep(POLL_INTERVAL)


def first_output(result: dict) -> str | None:
    out = result.get("output")
    if isinstance(out, list):
        return out[0] if out else None
    return out


# ─────────────────────────────────────────────────────────────────────────────
#  Stage 2 — animation via image_to_video
# ─────────────────────────────────────────────────────────────────────────────
# Map gen4_image image ratios → gen4.5 video ratios. gen4.5 video only accepts
# 1280:720 or 720:1280, so we pick the closest aspect.
_VIDEO_RATIO = {
    "720:1280":  "720:1280",
    "1080:1920": "720:1280",
    "1080:1440": "720:1280",
    "720:960":   "720:1280",
    "864:1184":  "720:1280",
    "1280:720":  "1280:720",
    "1920:1080": "1280:720",
    "1184:864":  "1280:720",
}


def video_ratio_for(image_ratio: str) -> str:
    return _VIDEO_RATIO.get(image_ratio, "720:1280" if "9:16" in image_ratio else "720:1280")


# ─────────────────────────────────────────────────────────────────────────────
#  Save to Drive
# ─────────────────────────────────────────────────────────────────────────────
def save_to_drive(folder_name: str, filename: str, video_url: str) -> str | None:
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


# ─────────────────────────────────────────────────────────────────────────────
#  Aspect ratio mapping (DB → image, then → video)
# ─────────────────────────────────────────────────────────────────────────────
_IMAGE_RATIO = {
    "9:16": "720:1280",
    "16:9": "1280:720",
    "1:1":  "1024:1024",
}


def image_ratio_for(shot: dict) -> str:
    raw = (shot.get("aspect_ratio") or "9:16").strip()
    return _IMAGE_RATIO.get(raw, raw if ":" in raw else "720:1280")


# ─────────────────────────────────────────────────────────────────────────────
#  Routing — pick the right tool for the shot
# ─────────────────────────────────────────────────────────────────────────────
def parse_chars(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [c.strip() for c in raw.split(",") if c.strip()]


# ─────────────────────────────────────────────────────────────────────────────
#  Per-shot-type editorial defaults — used when DB columns are unset.
# ─────────────────────────────────────────────────────────────────────────────
SHOT_TYPE_DEFAULTS: dict[str, dict] = {
    "establishing":     {"duration": 4,  "motion_intensity": "low"},
    "character_single": {"duration": 3,  "motion_intensity": "medium"},
    "two_shot":         {"duration": 6,  "motion_intensity": "medium"},
    "ensemble":         {"duration": 5,  "motion_intensity": "low"},   # 3-5 chars (band)
    "insert":           {"duration": 2,  "motion_intensity": "low"},
    "performance":      {"duration": 10, "motion_intensity": "low"},
    "match_cut":        {"duration": 2,  "motion_intensity": "high"},
    # Legacy fallbacks
    "environment":      {"duration": 4,  "motion_intensity": "low"},
    "dialogue":         {"duration": 4,  "motion_intensity": "medium"},
    "notation":         {"duration": 3,  "motion_intensity": "low"},
    "montage":          {"duration": 2,  "motion_intensity": "high"},
}

# Shot types that DON'T need character LoRAs — pure prompt → still.
NO_CHARACTER_SHOT_TYPES = {"insert", "establishing", "match_cut", "environment"}

# Replicate FLUX-LoRA stacking quality drops past 2 LoRAs. Any shot with more
# characters than this routes to needs_keyframe (human composite).
MAX_LORA_STACK = 2

# Translates motion_intensity into a short suffix appended to the animation
# prompt. Empty string for medium (default; no extra hint).
MOTION_PROMPT_SUFFIX: dict[str, str] = {
    "low":    " Camera holds nearly still; subtle ambient motion only.",
    "medium": "",
    "high":   " Camera pushes in or pans with quick, deliberate motion.",
}


def shot_type_default(shot: dict, key: str):
    st = (shot.get("shot_type") or "").strip()
    return SHOT_TYPE_DEFAULTS.get(st, {}).get(key)


def effective_duration(shot: dict) -> int:
    """API duration to send to image_to_video. Honors duration_seconds, then
    target_duration_seconds, then per-shot-type default, then VIDEO_DURATION.
    Clamps to [2, 10] (gen4.5/Seedance2 limits)."""
    raw = shot.get("duration_seconds")
    if raw is None:
        raw = shot.get("target_duration_seconds")
    if raw is None:
        raw = shot_type_default(shot, "duration")
    if raw is None:
        raw = VIDEO_DURATION
    return max(2, min(int(round(float(raw))), 10))


def effective_motion(shot: dict) -> str:
    return (shot.get("motion_intensity")
            or shot_type_default(shot, "motion_intensity")
            or "medium")


def apply_motion_to_prompt(prompt: str, intensity: str) -> str:
    """Append a short directive based on motion_intensity, unless the prompt
    already has explicit camera language."""
    if not prompt:
        return prompt
    suffix = MOTION_PROMPT_SUFFIX.get(intensity, "")
    if not suffix:
        return prompt
    if any(token in prompt.lower() for token in ("camera ", "push ", "pan ", "drift", "zoom ")):
        return prompt   # author already specified — don't override
    return prompt + suffix


def route_shot(shot: dict) -> str:
    """
    Route a runway-tool shot to one of these paths:

      "animate"          — keyframe locked: run image_to_video (Stage 2).
      "generate_still"   — no keyframe + characters' LoRAs all trained: call
                           Replicate with character LoRAs (Stage 1).
      "generate_insert"  — no keyframe + shot_type is character-free (insert,
                           establishing, environment, match_cut): call Replicate
                           with the INSERT_MODEL (no LoRAs needed).
      "needs_keyframe"   — fallback: human uploads still manually.

    Path A (omnihuman) is handled by run_batch.py, not this runner.
    """
    has_kf    = bool((shot.get("keyframe_image_url") or "").strip())
    chars     = parse_chars(shot.get("characters_used"))
    shot_type = (shot.get("shot_type") or "").strip()

    if has_kf:
        return "animate"

    # Character-free shot types use the INSERT_MODEL — no LoRAs needed.
    if shot_type in NO_CHARACTER_SHOT_TYPES and not chars:
        if INSERT_MODEL.get("lora"):
            return "generate_insert"
        return "needs_keyframe"

    if not chars:
        return "needs_keyframe"

    # Ensemble / multi-char beyond stack limit can't be auto-generated reliably
    # — even with all LoRAs trained, FLUX stacking past 2 produces mush. Route
    # those to manual composition (Photoshop/Photopea/Runway UI).
    if len(chars) > MAX_LORA_STACK:
        return "needs_keyframe"

    ready, _ = all_loras_ready(chars)
    if ready:
        return "generate_still"
    return "needs_keyframe"


# ─────────────────────────────────────────────────────────────────────────────
#  Process one shot — dispatch on routing
# ─────────────────────────────────────────────────────────────────────────────
def process_shot(shot: dict) -> None:
    db_id = shot["id"]
    name  = shot.get("shot_name", db_id)
    song  = shot.get("song_title", "Unknown Song")

    path = route_shot(shot)
    print(f"\n[{name}] start — song={song} path={path}")

    # Stop early for human-gated states. No API call.
    if path == "needs_keyframe":
        chars = parse_chars(shot.get("characters_used"))
        ready, missing = all_loras_ready(chars)
        if len(chars) > MAX_LORA_STACK:
            note = (f"Ensemble shot ({len(chars)} characters: {', '.join(chars)}). "
                    f"FLUX-LoRA stacking unreliable past {MAX_LORA_STACK} characters — "
                    f"compose this still manually (Runway UI / Photoshop) and upload.")
        elif missing and chars:
            note = (f"LoRAs not trained for {', '.join(missing)}. Train via Replicate or "
                    f"upload a manual keyframe.")
        elif not chars:
            note = "No characters set — upload a manual keyframe to animate."
        else:
            note = "Manual keyframe required."
        update_shot(db_id, status="needs_keyframe", review_notes=note)
        print(f"  → needs_keyframe — {note}")
        return

    prompt_raw = shot.get("runway_prompt") or shot.get("final_prompt") or ""
    if not prompt_raw:
        update_shot(db_id, status="failed", review_notes="runway_prompt empty")
        print("  FAILED — runway_prompt is empty")
        return

    img_ratio = image_ratio_for(shot)
    vid_ratio = video_ratio_for(img_ratio)
    duration  = effective_duration(shot)
    intensity = effective_motion(shot)
    print(f"  shot_type={shot.get('shot_type') or '(unset)'}  duration={duration}s  motion={intensity}")
    next_version = count_existing_runs(db_id) + 1
    base_name    = f"{song.replace(' ', '')}_{name.replace(' ', '')}_v{next_version}"
    drive_folder = f"{song} - Generated Shots"

    if path == "generate_still":
        update_shot(db_id, status="still_pending")
        run_replicate_still(shot, prompt_raw, img_ratio, db_id)
        return

    if path == "generate_insert":
        update_shot(db_id, status="still_pending")
        run_replicate_insert(shot, prompt_raw, img_ratio, db_id)
        return

    if path == "animate":
        update_shot(db_id, status="animating")
        # For animation, apply motion-intensity hint to the prompt unless the
        # author already specified camera language.
        animation_prompt = apply_motion_to_prompt(prompt_raw, intensity)
        run_animate_keyframe(shot, animation_prompt, vid_ratio, duration,
                             base_name, drive_folder, db_id, next_version)
        return

    # Should never hit; routing has covered everything above.
    update_shot(db_id, status="failed",
                review_notes=f"Unrouted shot — path={path}")
    print(f"  FAILED — unrouted ({path})")


# ─────────────────────────────────────────────────────────────────────────────
#  Stage 1 — Replicate still generation (LoRA-driven, character-faithful)
# ─────────────────────────────────────────────────────────────────────────────
_replicate_hdr = {
    "Authorization": f"Bearer {REPLICATE_API_TOKEN}" if REPLICATE_API_TOKEN else "",
    "Content-Type":  "application/json",
    # Replicate's edge blocks the default Python-urllib UA with 403. Set any
    # non-default UA and we're through.
    "User-Agent":    "roommates-runner/1.0",
}


# Translate @<name> tokens in the existing runway_prompt to the trained LoRA's
# trigger word (e.g. @maya → MAYA_RM). Names with no LoRA stay as @ tokens.
def trigger_translate_prompt(prompt: str) -> str:
    if not prompt:
        return prompt
    def repl(m: re.Match) -> str:
        raw = m.group(1)
        info = lookup_lora(raw)
        return info["trigger"] if info else m.group(0)
    return re.sub(r"@([A-Za-z][A-Za-z0-9_]*)", repl, prompt)


def replicate_aspect_ratio_for(img_ratio: str) -> str:
    """Replicate FLUX aspect_ratio strings (e.g. '9:16', '16:9', '1:1')."""
    if "1280:720" in img_ratio or "1920:1080" in img_ratio:
        return "16:9"
    if "1024:1024" in img_ratio or "960:960" in img_ratio:
        return "1:1"
    return "9:16"


def submit_replicate_still(prompt: str, lora_infos: list[dict], aspect_ratio: str) -> str:
    """
    Submit a still-image generation to Replicate using one or more character
    LoRAs. Returns the prediction id; caller polls.

    Each LoRA entry may carry an optional `extra_input` dict whose keys are
    merged into the input payload. Use this to override num_inference_steps,
    guidance, or any other model-specific knob without touching this function.

    Additional LoRAs (beyond the primary) are stacked via extra_lora /
    extra_lora_scale, the standard FLUX-LoRA-trainer field names.
    """
    if not REPLICATE_API_TOKEN:
        raise RuntimeError("REPLICATE_API_TOKEN not set")
    if not lora_infos:
        raise ValueError("submit_replicate_still requires at least one LoRA")

    primary = lora_infos[0]
    extra = lora_infos[1:]

    inp: dict = {
        "prompt":        prompt,
        "aspect_ratio":  aspect_ratio,
        "output_format": "png",
        "num_outputs":   1,
    }
    # Extra LoRAs: FLUX-LoRA-trainer outputs accept extra_lora + extra_lora_scale.
    if extra:
        inp["extra_lora"] = extra[0]["lora"]
        inp["extra_lora_scale"] = 0.85

    # Merge per-LoRA overrides last so they win against defaults above.
    inp.update(primary.get("extra_input") or {})

    body: dict = {"input": inp}
    if primary.get("version"):
        body["version"] = primary["version"]
        endpoint = f"{REPLICATE_BASE}/predictions"
    else:
        # Run the latest version of the named model
        endpoint = f"{REPLICATE_BASE}/models/{primary['lora']}/predictions"

    status, resp = http(endpoint, method="POST", headers=_replicate_hdr, data=body, timeout=60)
    if status >= 400:
        raise RuntimeError(f"Replicate submit failed [{status}]: {resp}")
    return resp.get("id") or resp.get("urls", {}).get("get", "").rstrip("/").split("/")[-1]


def poll_replicate(prediction_id: str) -> dict:
    started = time.time()
    while True:
        status, resp = http(
            f"{REPLICATE_BASE}/predictions/{prediction_id}",
            headers=_replicate_hdr, timeout=30,
        )
        if status != 200:
            raise RuntimeError(f"Replicate poll failed [{status}]: {resp}")
        state = (resp or {}).get("status")
        if state == "succeeded":
            return resp
        if state in ("failed", "canceled"):
            raise RuntimeError(f"Replicate prediction {state}: {resp.get('error') or resp}")
        if time.time() - started > POLL_TIMEOUT:
            raise TimeoutError(f"Replicate {prediction_id} stuck in {state} after {POLL_TIMEOUT}s")
        time.sleep(POLL_INTERVAL)


def run_replicate_insert(shot: dict, prompt_raw: str, img_ratio: str, db_id: str) -> None:
    """
    Stage 1 for character-free shot types (insert / establishing / match_cut /
    environment). Uses INSERT_MODEL (a generic Replicate model) — no LoRAs.
    The prompt should describe the object/setting; no @-tags expected.
    """
    aspect = replicate_aspect_ratio_for(img_ratio)
    print(f"  [Stage 1 / insert] {INSERT_MODEL['lora']} aspect={aspect}")
    print(f"           prompt={prompt_raw[:120]}…")

    last_err: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            pred_id = submit_replicate_still(prompt_raw, [INSERT_MODEL], aspect)
            print(f"  [Stage 1 / insert] prediction {pred_id}")
            result = poll_replicate(pred_id)
            output = result.get("output")
            still_url = output[0] if isinstance(output, list) and output else output
            if not still_url:
                raise RuntimeError(f"Replicate succeeded with no output URL: {result}")
            print(f"  [Stage 1 / insert] still OK → {still_url[:80]}…")

            update_shot(
                db_id,
                status             = "still_review",
                keyframe_image_url = still_url,
                review_notes       = f"Stage 1 insert: {INSERT_MODEL['lora']} {pred_id[:8]}",
            )
            return
        except Exception as e:
            last_err = e
            print(f"  [Stage 1 / insert] attempt {attempt} failed: {e}")
            time.sleep(3)

    update_shot(db_id, status="revision_needed",
                review_notes=f"Insert still failed after {MAX_ATTEMPTS}: {str(last_err)[:300]}")
    print(f"  FAILED — insert still exhausted")


def run_replicate_still(shot: dict, prompt_raw: str, img_ratio: str, db_id: str) -> None:
    """
    Stage 1: generate a still using the character LoRAs. On success: store the
    URL in keyframe_image_url and flip status to still_review (human gate).
    On failure: revision_needed with a useful note.
    """
    chars = parse_chars(shot.get("characters_used"))
    ready, missing = all_loras_ready(chars)
    if not ready:
        update_shot(db_id, status="needs_keyframe",
                    review_notes=f"LoRAs not trained for {', '.join(missing)} — upload manually.")
        return

    lora_infos = [lookup_lora(c) for c in chars]
    prompt = trigger_translate_prompt(prompt_raw)
    aspect = replicate_aspect_ratio_for(img_ratio)
    triggers = [info["trigger"] for info in lora_infos]
    print(f"  [Stage 1] Replicate still — LoRAs={[i['lora'] for i in lora_infos]} aspect={aspect}")
    print(f"           prompt={prompt[:120]}…  triggers={triggers}")

    last_err: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            pred_id = submit_replicate_still(prompt, lora_infos, aspect)
            print(f"  [Stage 1] prediction {pred_id}")
            result = poll_replicate(pred_id)
            output = result.get("output")
            if isinstance(output, list):
                still_url = output[0] if output else None
            else:
                still_url = output
            if not still_url:
                raise RuntimeError(f"Replicate succeeded with no output URL: {result}")
            print(f"  [Stage 1] still OK → {still_url[:80]}…")

            update_shot(
                db_id,
                status             = "still_review",
                keyframe_image_url = still_url,
                review_notes       = f"Stage 1: Replicate {pred_id[:8]} ({','.join(triggers)})",
            )
            return
        except Exception as e:
            last_err = e
            print(f"  [Stage 1] attempt {attempt} failed: {e}")
            time.sleep(3)

    update_shot(db_id, status="revision_needed",
                review_notes=f"Replicate still failed after {MAX_ATTEMPTS}: {str(last_err)[:300]}")
    print(f"  FAILED — Replicate exhausted")


# ─────────────────────────────────────────────────────────────────────────────
#  Stage 2 — Runway image_to_video animation (Seedance 2 by default)
# ─────────────────────────────────────────────────────────────────────────────
def submit_animation(image_url: str, prompt: str, ratio: str, duration: int,
                     model: str = DEFAULT_ANIMATION_MODEL) -> str:
    """
    Submit image_to_video. Default model is seedance2 (more aspect ratios,
    larger prompt budget). Falls through to the simple body shape both
    seedance2 and gen4.5 accept.
    """
    body = {
        "model":       model,
        "promptImage": image_url,
        "promptText":  prompt,
        "duration":    duration,
        "ratio":       ratio,
    }
    status, resp = http(
        f"{RUNWAY_BASE}/image_to_video",
        method="POST", headers=_runway_hdr, data=body, timeout=60,
    )
    if status >= 400:
        raise RuntimeError(f"Runway image_to_video failed [{status}]: {resp}")
    return resp["id"]


def run_animate_keyframe(shot: dict, prompt_raw: str, vid_ratio: str, duration: int,
                         base_name: str, drive_folder: str, db_id: str,
                         next_version: int) -> None:
    """
    Stage 2: animate the locked still via Runway image_to_video. Defaults to
    Seedance 2 unless the shot's animation_model column overrides.
    """
    try:
        keyframe_uri = resolve_keyframe_uri(shot["keyframe_image_url"])
    except Exception as e:
        update_shot(db_id, status="needs_keyframe",
                    review_notes=f"keyframe_image_url unusable: {str(e)[:300]}")
        print(f"  FAILED — bad keyframe_image_url: {e}")
        return

    # Animation prompt: trigger-translated so motion descriptions reference
    # the same character names. (Animation model doesn't use LoRAs but the
    # consistent naming keeps logs readable.)
    prompt = trigger_translate_prompt(prompt_raw)
    model  = (shot.get("animation_model") or DEFAULT_ANIMATION_MODEL).strip() or DEFAULT_ANIMATION_MODEL

    last_err: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        print(f"  [Stage 2] attempt {attempt}/{MAX_ATTEMPTS}")
        try:
            print(f"    animate: {model} @ {vid_ratio}, {duration}s, "
                  f"keyframe={keyframe_uri[:80]}…")
            an_task = submit_animation(keyframe_uri, prompt, vid_ratio, duration, model=model)
            an_result = poll_task(an_task)
            video_url = first_output(an_result)
            if not video_url:
                raise RuntimeError(f"Animation task succeeded but no output URL: {an_result}")
            print(f"    animate OK → {video_url[:80]}…")

            filename = f"{base_name}.mp4"
            folder_url = save_to_drive(drive_folder, filename, video_url)
            update_shot(
                db_id,
                status            = "review_pending",
                asset_url         = video_url,
                drive_folder_url  = folder_url or shot.get("drive_folder_url"),
                review_notes      = f"Stage 2: {model} → an={an_task[:8]} v{next_version}",
                reviewer_feedback = None,
            )
            record_generation_run(shot, video_url, filename, folder_url, duration, keyframe_uri)
            print(f"  DONE → v{next_version} → {video_url[:80]}…")
            return
        except Exception as e:
            last_err = e
            print(f"  attempt {attempt} failed: {e}")
            time.sleep(5)

    update_shot(
        db_id, status="revision_needed",
        review_notes=f"Animate failed after {MAX_ATTEMPTS}: {str(last_err)[:300]}",
    )
    print(f"  FAILED — animate exhausted")


# ─────────────────────────────────────────────────────────────────────────────
#  Main
# ─────────────────────────────────────────────────────────────────────────────
def main() -> None:
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
        scene = s.get("scene_ref") or "—"
        path  = route_shot(s)
        print(f"  {i}. {s.get('shot_name', '?'):<32} song={s.get('song_title', '?'):<22} "
              f"dur={s.get('duration_seconds')}s  chars={len(chars)} ({chars_raw})  "
              f"scene={scene}  path={path}")

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
