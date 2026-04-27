#!/usr/bin/env python3
"""
hook_worker.py — Cloud, shot-driven hook generator.

Reads `production_queue` rows that need audio (audio_url IS NULL) and
generates a section-matched hook clip for each: the right slice of the
right song, capped at the shot's duration_seconds (max 15s for shorts).

First time a song is encountered, the worker:
  1. Downloads the full song from the Drive INPUT_FOLDER
  2. Runs librosa structural segmentation to detect verse/chorus/bridge boundaries
  3. Persists the result to songs.sections (JSONB) so subsequent shots reuse it
  4. The persisted boundaries can be hand-edited via SQL if auto-detection misses

Per-shot section selection uses fuzzy matching on production_queue.song_section.
"Verse 1 / Pre-Chorus mood" → matches "verse_1" or "pre_chorus_1" keys.
"Final Chorus – Lift"      → matches "final_lift" or "chorus_3".

Outputs land in OUTPUT_FOLDER named: {song_slug}_{section}_{N}s.mp3

Env vars (set as GitHub secrets / variables):
    APPS_SCRIPT_URL   (secret) — Drive webapp
    SUPABASE_URL      (secret)
    SUPABASE_KEY      (secret) — service-role or anon key with write access
    INPUT_FOLDER      (var)    — Drive folder with full songs (default: 'Roommates - Full Songs')
    OUTPUT_FOLDER     (var)    — Drive folder for hooks       (default: 'Roommates - Hooks')
    MAX_HOOK_SECONDS  (var)    — cap per-shot hook length     (default: 15)

Idempotent — only processes rows with audio_url IS NULL.
"""

import base64
import json
import os
import re
import sys
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

import librosa
import numpy as np
import pyloudnorm as pyln
import soundfile as sf
from pydub import AudioSegment


# ─── Config ────────────────────────────────────────────────────────────────
APPS_SCRIPT_URL  = os.environ.get("APPS_SCRIPT_URL")
SUPABASE_URL     = os.environ.get("SUPABASE_URL")
SUPABASE_KEY     = os.environ.get("SUPABASE_KEY")
INPUT_FOLDER     = os.environ.get("INPUT_FOLDER",  "Roommates - Full Songs")
OUTPUT_FOLDER    = os.environ.get("OUTPUT_FOLDER", "Roommates - Hooks")
MAX_HOOK_SECONDS = int(os.environ.get("MAX_HOOK_SECONDS", "15"))

FADE_SECONDS = 0.5      # shorter fades for short clips
TARGET_LUFS  = -14.0
HTTP_TIMEOUT = 300

missing = [k for k, v in [
    ("APPS_SCRIPT_URL", APPS_SCRIPT_URL),
    ("SUPABASE_URL",    SUPABASE_URL),
    ("SUPABASE_KEY",    SUPABASE_KEY),
] if not v]
if missing:
    sys.exit(f"Missing required env vars: {', '.join(missing)}")

SB_HEADERS = {
    "apikey":        SUPABASE_KEY,
    "Authorization": f"Bearer {SUPABASE_KEY}",
    "Content-Type":  "application/json",
    "Prefer":        "return=representation",
}


# ─── HTTP helper ───────────────────────────────────────────────────────────
def _http(method, url, payload=None, headers=None, timeout=HTTP_TIMEOUT):
    body = None
    h = dict(headers or {})
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        h.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, method=method, headers=h, data=body)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", errors="replace")
            status = resp.getcode()
    except urllib.error.HTTPError as e:
        text = e.read().decode("utf-8", errors="replace")
        status = e.code
    try:
        return status, json.loads(text)
    except ValueError:
        return status, text


# ─── Apps Script client ────────────────────────────────────────────────────
def list_drive_folder(folder_name):
    q = urllib.parse.urlencode({"action": "list", "folder": folder_name})
    s, r = _http("GET", f"{APPS_SCRIPT_URL}?{q}")
    if s != 200 or "error" in r:
        raise RuntimeError(f"Drive list failed: {r}")
    return r.get("files", [])


def download_drive_file(file_id):
    q = urllib.parse.urlencode({"action": "download", "fileId": file_id})
    s, r = _http("GET", f"{APPS_SCRIPT_URL}?{q}")
    if s != 200 or "error" in r:
        raise RuntimeError(f"Drive download failed: {r}")
    return r["name"], r["mimeType"], base64.b64decode(r["contentBase64"])


def upload_drive_file(folder_name, filename, content_bytes, mime_type="audio/mpeg"):
    payload = {
        "action":        "upload",
        "folder":        folder_name,
        "filename":      filename,
        "mimeType":      mime_type,
        "contentBase64": base64.b64encode(content_bytes).decode("ascii"),
    }
    s, r = _http("POST", APPS_SCRIPT_URL, payload=payload)
    if s != 200 or "error" in r:
        raise RuntimeError(f"Drive upload failed: {r}")
    return r


# ─── Supabase client ───────────────────────────────────────────────────────
def fetch_pending_audio_shots():
    """Find production_queue rows that need an audio hook."""
    q = urllib.parse.urlencode({
        "audio_url": "is.null",
        "song_id":   "not.is.null",
        "select":    "id,song_id,song_title,shot_name,song_section,duration_seconds",
        "order":     "created_at.asc",
    })
    s, r = _http("GET", f"{SUPABASE_URL}/rest/v1/production_queue?{q}", headers=SB_HEADERS)
    if s != 200:
        raise RuntimeError(f"Supabase fetch failed [{s}]: {r}")
    return r or []


def fetch_song(song_id):
    q = urllib.parse.urlencode({
        "id":     f"eq.{song_id}",
        "select": "id,song_title,sections,audio_drive_filename",
    })
    s, r = _http("GET", f"{SUPABASE_URL}/rest/v1/songs?{q}", headers=SB_HEADERS)
    if s != 200 or not r:
        raise RuntimeError(f"Song fetch failed for {song_id}: {r}")
    return r[0]


def update_song_sections(song_id, sections):
    s, r = _http(
        "PATCH",
        f"{SUPABASE_URL}/rest/v1/songs?id=eq.{song_id}",
        payload={"sections": sections},
        headers=SB_HEADERS,
    )
    if s >= 400:
        print(f"  ⚠  song.sections update failed [{s}]: {r}")


def update_shot_audio(shot_id, audio_url, section_key):
    s, r = _http(
        "PATCH",
        f"{SUPABASE_URL}/rest/v1/production_queue?id=eq.{shot_id}",
        payload={"audio_url": audio_url, "audio_section_used": section_key},
        headers=SB_HEADERS,
    )
    if s >= 400:
        print(f"  ⚠  shot audio update failed [{s}]: {r}")


# ─── Section detection (librosa structural segmentation) ───────────────────
def detect_sections(audio_path: Path, total_duration: float) -> dict:
    """
    Return a dict of canonical section names → {start, end} ranges.
    Uses energy + repetition heuristics on librosa-detected structural boundaries.
    """
    y, sr = librosa.load(str(audio_path), mono=True, sr=22050)

    # Beat tracking + chroma for structural similarity
    _tempo, beats = librosa.beat.beat_track(y=y, sr=sr)
    if len(beats) < 8:
        # Too short / not rhythmic enough — return one big "song" segment
        return {"chorus_1": {"start": 0.0, "end": total_duration}}

    chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=512)
    beat_chroma = librosa.util.sync(chroma, beats, aggregate=np.median)

    # Aim for ~6-8 segments — typical pop structure
    target_segments = min(8, max(4, len(beats) // 16))
    bounds = librosa.segment.agglomerative(beat_chroma, k=target_segments)
    bound_times = librosa.frames_to_time(beats[bounds], sr=sr)
    bound_times = sorted(set([0.0] + [float(t) for t in bound_times] + [float(total_duration)]))

    # Build segments + per-segment energy
    rms = librosa.feature.rms(y=y, hop_length=512)[0]
    times = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=512)
    segments = []
    for i in range(len(bound_times) - 1):
        st, en = bound_times[i], bound_times[i + 1]
        if en - st < 3.0:
            continue  # skip tiny segments
        s_idx = max(0, int(st * sr / 512))
        e_idx = min(len(rms), int(en * sr / 512))
        if e_idx <= s_idx:
            continue
        e_mean = float(np.mean(rms[s_idx:e_idx]))
        segments.append({"start": float(st), "end": float(en), "duration": float(en - st), "energy": e_mean})

    if not segments:
        return {"chorus_1": {"start": 0.0, "end": total_duration}}

    return classify_segments(segments, total_duration)


def classify_segments(segments, total_duration):
    """Map segments to canonical names using energy + position heuristics."""
    energies = [s["energy"] for s in segments]
    median_e = float(np.median(energies)) if energies else 0.0

    sections = {}
    verse_n = 0
    chorus_n = 0
    pre_chorus_n = 0

    for i, seg in enumerate(segments):
        e_ratio = seg["energy"] / median_e if median_e > 0 else 1.0
        is_loud   = e_ratio > 1.10
        is_quiet  = e_ratio < 0.92
        first_q   = seg["start"] < total_duration * 0.25
        last_q    = seg["start"] > total_duration * 0.75
        last_15p  = seg["start"] > total_duration * 0.85

        # First short low-energy segment = intro
        if i == 0 and seg["duration"] < 14 and is_quiet:
            sections["intro"] = {"start": seg["start"], "end": seg["end"]}
            continue

        # Late high-energy = final lift / outro chorus
        if last_15p and is_loud:
            sections["final_lift"] = {"start": seg["start"], "end": seg["end"]}
            continue

        # High-energy elsewhere = chorus
        if is_loud:
            chorus_n += 1
            sections[f"chorus_{chorus_n}"] = {"start": seg["start"], "end": seg["end"]}
            continue

        # Low-energy elsewhere = verse
        if is_quiet:
            verse_n += 1
            sections[f"verse_{verse_n}"] = {"start": seg["start"], "end": seg["end"]}
            continue

        # Mid-energy in last quarter = bridge
        if last_q and "bridge" not in sections:
            sections["bridge"] = {"start": seg["start"], "end": seg["end"]}
            continue

        # Otherwise = pre_chorus
        pre_chorus_n += 1
        sections[f"pre_chorus_{pre_chorus_n}"] = {"start": seg["start"], "end": seg["end"]}

    # Ensure at least one chorus exists (fallback for songs that don't fit the pattern)
    if not any(k.startswith("chorus") for k in sections):
        loudest = max(segments, key=lambda s: s["energy"])
        sections["chorus_1"] = {"start": loudest["start"], "end": loudest["end"]}

    return sections


# ─── Section matching ──────────────────────────────────────────────────────
def normalize_key(text):
    return re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")


# Map common shot.song_section phrases → preferred section keys (in order)
_SECTION_KEYWORDS = [
    ("final_lift",      ["final_lift", "final_chorus", "outro_chorus", "lift"]),
    ("bridge",          ["bridge"]),
    ("pre_chorus_1",    ["pre_chorus_1", "pre_chorus"]),
    ("chorus_1",        ["chorus_1", "chorus", "drop", "hook"]),
    ("verse_1",         ["verse_1", "verse"]),
    ("intro",           ["intro"]),
]


def match_section(shot_section_text: str, available: dict) -> tuple:
    """
    Pick the best section key from `available` that matches the shot's
    song_section text. Returns (key, range_dict) or (None, None).
    """
    norm = normalize_key(shot_section_text)
    if not norm:
        # Default: chorus_1 if available, else first key
        if "chorus_1" in available:
            return "chorus_1", available["chorus_1"]
        first = next(iter(available), None)
        return (first, available[first]) if first else (None, None)

    # Direct key hit
    if norm in available:
        return norm, available[norm]

    # Substring keyword match — try in priority order
    for canonical, aliases in _SECTION_KEYWORDS:
        for alias in aliases:
            if alias in norm:
                if canonical in available:
                    return canonical, available[canonical]
                # Try numbered variants
                for k in available:
                    if k.startswith(alias):
                        return k, available[k]

    # Word-overlap fallback
    for k in available:
        if k in norm or any(part in norm for part in k.split("_")):
            return k, available[k]

    # Nothing matched — fall back to chorus_1 or first
    if "chorus_1" in available:
        return "chorus_1", available["chorus_1"]
    first = next(iter(available), None)
    return (first, available[first]) if first else (None, None)


# ─── Audio extraction ──────────────────────────────────────────────────────
def extract_clip(audio_path: Path, start: float, duration: float, out_path: Path) -> dict:
    """
    Cut [start, start+duration] from audio_path, fade in/out, normalize to
    -14 LUFS, export as MP3 to out_path.
    """
    y, sr = librosa.load(str(audio_path), mono=False, sr=None)
    if y.ndim == 1:
        y = np.stack([y, y])

    end = start + duration
    s_idx = max(0, int(start * sr))
    e_idx = min(int(end * sr), y.shape[1])
    clip = y[:, s_idx:e_idx].copy().T  # (samples, channels)

    # Fades
    fade_samples = int(FADE_SECONDS * sr)
    n = clip.shape[0]
    if fade_samples * 2 < n:
        fade_in = np.linspace(0.0, 1.0, fade_samples)[:, None]
        fade_out = np.linspace(1.0, 0.0, fade_samples)[:, None]
        clip[:fade_samples] *= fade_in
        clip[-fade_samples:] *= fade_out

    # Loudness normalize to -14 LUFS
    try:
        meter = pyln.Meter(sr)
        loudness = meter.integrated_loudness(clip)
        if not (np.isinf(loudness) or np.isnan(loudness)):
            clip = pyln.normalize.loudness(clip, loudness, TARGET_LUFS)
    except Exception:
        pass

    # Prevent clipping
    peak = float(np.max(np.abs(clip)))
    if peak > 0.99:
        clip *= 0.99 / peak

    # WAV → MP3 via pydub (needs ffmpeg)
    tmp_wav = out_path.with_suffix(".tmp.wav")
    sf.write(str(tmp_wav), clip, sr)
    AudioSegment.from_wav(str(tmp_wav)).export(str(out_path), format="mp3", bitrate="192k")
    tmp_wav.unlink()

    return {"start": round(start, 2), "end": round(end, 2), "duration": round(duration, 2)}


# ─── Main loop ─────────────────────────────────────────────────────────────
def slugify(text):
    return re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")


def find_song_file_in_drive(drive_files, song_title, audio_drive_filename):
    """Match a song to a Drive file by exact filename or fuzzy title match."""
    if audio_drive_filename:
        for f in drive_files:
            if f["name"] == audio_drive_filename:
                return f
    target = slugify(song_title)
    for f in drive_files:
        stem = Path(f["name"]).stem
        if slugify(stem) == target:
            return f
    # Substring fallback
    for f in drive_files:
        if target in slugify(Path(f["name"]).stem):
            return f
    return None


def main():
    print(f"Worker config:")
    print(f"  INPUT_FOLDER:     {INPUT_FOLDER}")
    print(f"  OUTPUT_FOLDER:    {OUTPUT_FOLDER}")
    print(f"  MAX_HOOK_SECONDS: {MAX_HOOK_SECONDS}")
    print()

    shots = fetch_pending_audio_shots()
    if not shots:
        print("No production_queue rows need audio. Exiting.")
        return

    print(f"Found {len(shots)} shot(s) needing audio:")
    for s in shots:
        print(f"  - {s['song_title']} / {s['shot_name']} (section: {s.get('song_section') or '?'}, dur: {s.get('duration_seconds') or '?'}s)")
    print()

    drive_files = list_drive_folder(INPUT_FOLDER)
    existing_hooks = {f["name"] for f in list_drive_folder(OUTPUT_FOLDER)}
    print(f"Drive: {len(drive_files)} song(s) in input, {len(existing_hooks)} hook(s) already in output")
    print()

    # Cache downloaded songs + their detected sections so we don't re-download
    # if multiple shots use the same song
    song_audio_cache = {}   # song_id → Path on tmp disk
    song_meta_cache = {}    # song_id → fetched song row

    with tempfile.TemporaryDirectory() as tmpdir:
        tmp = Path(tmpdir)

        for i, shot in enumerate(shots, 1):
            print(f"[{i}/{len(shots)}] {shot['song_title']} — {shot['shot_name']}")
            try:
                song_id = shot["song_id"]
                if song_id not in song_meta_cache:
                    song_meta_cache[song_id] = fetch_song(song_id)
                song = song_meta_cache[song_id]

                # Locate the song's audio file in Drive
                drive_file = find_song_file_in_drive(drive_files, song["song_title"], song.get("audio_drive_filename"))
                if not drive_file:
                    print(f"  ⚠  no matching audio file in '{INPUT_FOLDER}' for '{song['song_title']}' — skipping")
                    continue

                # Download (once per song)
                if song_id not in song_audio_cache:
                    print(f"  downloading {drive_file['name']}…")
                    name, _mime, data = download_drive_file(drive_file["id"])
                    audio_path = tmp / name
                    audio_path.write_bytes(data)
                    song_audio_cache[song_id] = audio_path
                else:
                    audio_path = song_audio_cache[song_id]

                # Detect sections (once per song, persist to DB)
                sections = song.get("sections")
                if not sections:
                    print(f"  detecting sections (first time for this song)…")
                    duration_s = librosa.get_duration(path=str(audio_path))
                    sections = detect_sections(audio_path, duration_s)
                    print(f"    detected: {list(sections.keys())}")
                    update_song_sections(song_id, sections)
                    song["sections"] = sections
                    song_meta_cache[song_id] = song
                else:
                    print(f"  using stored sections: {list(sections.keys())}")

                # Match the shot's section
                section_key, section_range = match_section(shot.get("song_section") or "", sections)
                if not section_range:
                    print(f"  ⚠  no section match for '{shot.get('song_section')}' — skipping")
                    continue
                print(f"  matched section: {section_key} ({section_range['start']:.1f}–{section_range['end']:.1f}s)")

                # Compute clip range — center within the section, clamp to MAX_HOOK_SECONDS
                want = min(int(shot.get("duration_seconds") or 10), MAX_HOOK_SECONDS)
                section_dur = section_range["end"] - section_range["start"]
                clip_dur = min(want, section_dur)
                # Start at the section start, but if the section is much longer, center within it
                if section_dur > clip_dur + 4:
                    clip_start = section_range["start"] + (section_dur - clip_dur) / 2
                else:
                    clip_start = section_range["start"]

                # Build output filename
                out_name = f"{slugify(song['song_title'])}_{section_key}_{int(clip_dur)}s.mp3"
                out_path = tmp / out_name

                # Skip if already in Drive
                if out_name in existing_hooks:
                    print(f"  hook already exists in Drive: {out_name}")
                else:
                    meta = extract_clip(audio_path, clip_start, clip_dur, out_path)
                    print(f"  extracted {meta['start']}s–{meta['end']}s ({out_path.stat().st_size:,} bytes)")
                    up = upload_drive_file(OUTPUT_FOLDER, out_name, out_path.read_bytes(), "audio/mpeg")
                    audio_url = up.get("fileUrl") or up.get("folderUrl")
                    print(f"  uploaded → {audio_url}")
                    existing_hooks.add(out_name)

                # Resolve the Drive URL even if hook pre-existed
                if out_name in existing_hooks and out_name not in {f["name"] for f in [drive_file]}:
                    # Find the existing hook's URL by re-listing (only if we didn't just upload)
                    if "audio_url" not in locals() or not audio_url:
                        out_files = list_drive_folder(OUTPUT_FOLDER)
                        existing = next((f for f in out_files if f["name"] == out_name), None)
                        # Apps Script list returns id but not URL — construct manually
                        audio_url = f"https://drive.google.com/file/d/{existing['id']}/view" if existing else None

                update_shot_audio(shot["id"], audio_url, section_key)
                print(f"  ✓ shot updated")

            except Exception as e:
                print(f"  FAILED: {e}")

    print("\nWorker done.")


if __name__ == "__main__":
    main()
