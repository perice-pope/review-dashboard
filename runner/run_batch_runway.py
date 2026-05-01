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

# Local registry — single source of truth for character/scene images.
sys.path.insert(0, str(Path(__file__).parent.resolve()))
from assets import CHARACTERS, SCENES, lookup_character, lookup_scene  # noqa: E402

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

SUPABASE_URL     = _ENV.get("SUPABASE_URL")     or os.environ.get("SUPABASE_URL")
SUPABASE_KEY     = _ENV.get("SUPABASE_KEY")     or os.environ.get("SUPABASE_KEY")
RUNWAY_API_KEY   = _ENV.get("RUNWAY_API_KEY")   or os.environ.get("RUNWAY_API_KEY")
DRIVE_WEBAPP_URL = _ENV.get("DRIVE_WEBAPP_URL") or os.environ.get("DRIVE_WEBAPP_URL", "")

RUNWAY_BASE    = "https://api.dev.runwayml.com/v1"
RUNWAY_VERSION = "2024-11-06"

KEYFRAME_MODEL = "gen4_image"   # supports referenceImages, up to 3
VIDEO_MODEL    = "gen4.5"       # image_to_video — animates the keyframe

REF_CAP        = 3              # Runway hard limit per text_to_image call
MAX_ATTEMPTS   = 3
POLL_INTERVAL  = 10
POLL_TIMEOUT   = 60 * 8
VIDEO_DURATION = 10             # seconds; gen4.5 takes integers 2..10

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
    Reset shots stuck in 'generating' for > STUCK_GENERATING_MINUTES back to
    'revision_needed' so they get retried. Catches the case where a previous
    runner was cancelled or crashed after flipping status to generating but
    before completing.
    """
    cutoff = (datetime.now(timezone.utc)
              - timedelta(minutes=STUCK_GENERATING_MINUTES)).isoformat()
    q = urllib.parse.urlencode({
        "primary_tool": "eq.runway_gen4_references",
        "status":       "eq.generating",
        "updated_at":   f"lt.{cutoff}",
        "select":       "id,shot_name,updated_at",
    })
    status, resp = http(f"{SUPABASE_URL}/rest/v1/production_queue?{q}", headers=SB_HEADERS)
    if status != 200 or not isinstance(resp, list):
        return
    for shot in resp:
        print(f"  ⏪  reviving stuck shot {shot.get('shot_name')} "
              f"(generating since {shot.get('updated_at')})")
        update_shot(shot["id"], status="revision_needed",
                    review_notes="Auto-revived: previous runner did not complete")


def fetch_ready_shots():
    recover_stuck_shots()
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


def submit_animation(image_url: str, prompt: str, ratio: str, duration: int) -> str:
    body = {
        "model":       VIDEO_MODEL,
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
#  Process one shot
# ─────────────────────────────────────────────────────────────────────────────
def process_shot(shot: dict) -> None:
    db_id = shot["id"]
    name  = shot.get("shot_name", db_id)
    song  = shot.get("song_title", "Unknown Song")

    print(f"\n[{name}] start — song={song}")
    update_shot(db_id, status="generating")

    prompt_raw = shot.get("runway_prompt") or shot.get("final_prompt") or ""
    if not prompt_raw:
        update_shot(db_id, status="failed", review_notes="runway_prompt empty")
        print("  FAILED — runway_prompt is empty")
        return

    # Resolve refs
    try:
        refs, warns = build_reference_images(shot)
    except Exception as e:
        update_shot(db_id, status="revision_needed",
                    review_notes=f"Ref resolution failed: {str(e)[:400]}")
        print(f"  FAILED during ref resolution: {e}")
        return
    for w in warns:
        print(f"  ⚠  {w}")
    print(f"  refs ({len(refs)}): {[r['tag'] for r in refs]}")

    # Normalize @Tag casing in the prompt and warn on unbound refs
    prompt = normalize_prompt_tags(prompt_raw, refs)
    for w in validate_prompt_against_refs(prompt, refs):
        print(f"  ⚠  {w}")

    img_ratio = image_ratio_for(shot)
    vid_ratio = video_ratio_for(img_ratio)
    duration  = max(2, min(int(shot.get("duration_seconds") or VIDEO_DURATION), 10))

    next_version = count_existing_runs(db_id) + 1
    base_name = f"{song.replace(' ', '')}_{name.replace(' ', '')}_gen4_v{next_version}"
    drive_folder = f"{song} - Generated Shots"

    last_err: Exception | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        print(f"  attempt {attempt}/{MAX_ATTEMPTS}")
        try:
            # Stage 1 — keyframe
            print(f"    keyframe: {KEYFRAME_MODEL} @ {img_ratio}, refs={[r['tag'] for r in refs]}")
            kf_task = submit_keyframe(prompt, refs, ratio=img_ratio)
            kf_result = poll_task(kf_task)
            keyframe_url = first_output(kf_result)
            if not keyframe_url:
                raise RuntimeError(f"Keyframe task succeeded but no output URL: {kf_result}")
            print(f"    keyframe OK → {keyframe_url[:80]}…")

            # Stage 2 — animation
            print(f"    animate:  {VIDEO_MODEL} @ {vid_ratio}, {duration}s")
            an_task = submit_animation(keyframe_url, prompt, vid_ratio, duration)
            an_result = poll_task(an_task)
            video_url = first_output(an_result)
            if not video_url:
                raise RuntimeError(f"Animation task succeeded but no output URL: {an_result}")
            print(f"    animate OK → {video_url[:80]}…")

            # Persist
            filename = f"{base_name}.mp4"
            folder_url = save_to_drive(drive_folder, filename, video_url)
            update_shot(
                db_id,
                status            = "review_pending",
                asset_url         = video_url,
                drive_folder_url  = folder_url or shot.get("drive_folder_url"),
                review_notes      = (f"Two-stage Gen-4: kf={kf_task[:8]} an={an_task[:8]} "
                                     f"refs=[{','.join(r['tag'] for r in refs)}] v{next_version}"),
                reviewer_feedback = None,
            )
            record_generation_run(shot, video_url, filename, folder_url, duration, keyframe_url)
            print(f"  DONE → v{next_version} → {video_url[:80]}…")
            return

        except Exception as e:
            last_err = e
            print(f"  attempt {attempt} failed: {e}")
            time.sleep(5)

    update_shot(
        db_id, status="revision_needed",
        review_notes=f"Two-stage Gen-4 failed after {MAX_ATTEMPTS} attempts: {str(last_err)[:300]}",
    )
    print(f"  FAILED — all attempts exhausted")


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
        print(f"  {i}. {s.get('shot_name', '?'):<32} song={s.get('song_title', '?'):<22} "
              f"dur={s.get('duration_seconds')}s  chars={len(chars)} ({chars_raw})  scene={scene}")

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
