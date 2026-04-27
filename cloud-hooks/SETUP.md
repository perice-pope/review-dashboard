# Cloud Hook Pipeline — Shot-Driven, Section-Aware

GitHub Actions runs `hook_worker.py` every 10 minutes. For each
`production_queue` row that's missing `audio_url`, it:

1. Looks up the song's full audio file in your Drive `INPUT_FOLDER`
2. Auto-detects section boundaries (verse/chorus/bridge) the first time a
   song is seen, and persists them to `songs.sections` (JSONB)
3. Fuzzy-matches the shot's `song_section` text to a section key
4. Extracts the right slice (capped at `MAX_HOOK_SECONDS`, default 15s)
5. Uploads to your Drive `OUTPUT_FOLDER` as `{song_slug}_{section}_{N}s.mp3`
6. Updates `production_queue.audio_url` and `audio_section_used`

```
Drop a song into Drive  →  Ship a shot to production_queue
                            (cron picks it up within 10 min)
                            ↓
                       Worker auto-detects sections (first time only)
                            ↓
                       Slice extracted, uploaded to Drive Hooks folder
                            ↓
                       production_queue.audio_url populated
                            ↓
                       Editor pulls the hook by URL and muxes in CapCut
```

---

## Files in this folder

```
cloud-hooks/
├── apps-script.gs       # Drive webapp — REPLACES your existing one
├── hook_worker.py        # The worker
├── requirements.txt       # Python deps
└── SETUP.md               # this file

(workflow file lives at the repo root: .github/workflows/generate-hooks.yml)
```

---

## One-time setup (~30 minutes)

### 1. Drive folder structure

Two folders side by side at the root of My Drive (or under a parent — see
`ROOT_FOLDER_ID` in `apps-script.gs`):

```
My Drive/
├── Roommates - Full Songs/    ← drop full songs here (any audio format)
└── Roommates - Hooks/          ← worker writes hook clips here
```

The worker creates either folder if it doesn't exist. Folder names are
configurable via GitHub variables.

### 2. Replace your existing Drive Apps Script

Your existing webapp (the one that gave you `DRIVE_WEBAPP_URL`) currently
just handles `POST {folderName, videos: [[name, url]]}`. The new
`apps-script.gs` preserves that exact behavior **and** adds the new actions
the worker needs (list / download / upload-by-base64).

1. Open your existing Apps Script project at `script.google.com`
2. Replace the entire script with the contents of `apps-script.gs`
3. Deploy → Manage deployments → click the pencil icon → **New version** → Deploy
4. The same `DRIVE_WEBAPP_URL` keeps working — `run_batch_runway.py`, etc.,
   don't need any changes

> **If your existing script does anything beyond the legacy video-save**
> (e.g. custom email, calendar, etc.), preserve those pieces by pasting
> them above the dispatchers and routing from `doPost`.

### 3. GitHub repo + secrets

The repo already exists: `https://github.com/perice-pope/review-dashboard`.
The workflow lives at `.github/workflows/generate-hooks.yml` at the repo
root.

In the repo: **Settings → Secrets and variables → Actions**

Add three **secrets**:
- `APPS_SCRIPT_URL` — your Drive webapp URL
- `SUPABASE_URL` — `https://xrtyllishxovdpazjdco.supabase.co`
- `SUPABASE_KEY` — your Supabase service-role or anon key (must allow
  reads + writes on `songs` and `production_queue`)

Optional **variables** (skip these to use defaults):
- `INPUT_FOLDER` — Drive folder with full songs (default: `Roommates - Full Songs`)
- `OUTPUT_FOLDER` — Drive folder for hooks (default: `Roommates - Hooks`)
- `MAX_HOOK_SECONDS` — cap (default: `15`)

### 4. First manual run

Actions tab → **Generate Hook Clips** → Run workflow. Watch the logs:
- `[1/N] Spring Thaw — Frosted Window Thaw`
- `downloading SpringThaw.mp3…`
- `detecting sections (first time for this song)…`
- `detected: ['intro', 'verse_1', 'pre_chorus_1', 'chorus_1', 'verse_2', 'chorus_2', 'bridge', 'final_lift']`
- `matched section: verse_1 (8.2–32.4s)`
- `extracted 19.3s–29.3s (218,000 bytes)`
- `uploaded → https://drive.google.com/...`
- `✓ shot updated`

After that, the cron handles it automatically.

---

## How section detection works

First time the worker encounters a song, it runs `librosa.segment.agglomerative`
on beat-synchronous chroma features to find structural boundaries, then
classifies each segment using two heuristics:

- **Energy** (RMS) — high-energy segments → chorus, low-energy → verse
- **Position** — early/mid/late determines `verse_1` vs `verse_2`,
  `chorus_1` vs `final_lift`, etc.

The result is stored in `songs.sections` as JSONB. Subsequent shots reuse
the cached boundaries — no re-detection cost.

### Section keys produced

| Key | What it usually catches |
|---|---|
| `intro` | Quiet opening segment, < 14s |
| `verse_1`, `verse_2` | Lower-energy non-chorus segments |
| `pre_chorus_1`, `pre_chorus_2` | Mid-energy build segments |
| `chorus_1`, `chorus_2` | High-energy repeated segments |
| `bridge` | Mid-energy unique segment in the back half |
| `final_lift` | High-energy segment in the last 15% of the track |

Auto-detection isn't perfect on every song. If a song picks weirdly, override.

### Manual override

If auto-detection misclassifies, edit `songs.sections` directly. Connect to
Supabase and run:

```sql
UPDATE public.songs
SET sections = '{
  "intro":         {"start": 0,    "end": 8.5},
  "verse_1":       {"start": 8.5,  "end": 32.0},
  "pre_chorus_1":  {"start": 32.0, "end": 48.0},
  "chorus_1":      {"start": 48.0, "end": 80.0},
  "verse_2":       {"start": 80.0, "end": 104.0},
  "chorus_2":      {"start": 104.0,"end": 136.0},
  "bridge":        {"start": 136.0,"end": 160.0},
  "final_lift":    {"start": 160.0,"end": 200.0}
}'::jsonb
WHERE song_title = 'Spring Thaw';
```

To force re-detection on the next run, set `sections = NULL`.

To force re-extraction of a shot's hook (e.g. after manually correcting
sections), null out the shot's audio_url:

```sql
UPDATE public.production_queue
SET audio_url = NULL, audio_section_used = NULL
WHERE shot_name = 'Frosted Window Thaw';
```

The next worker run will pick it up.

---

## Section matching logic

The shot's `song_section` text is fuzzy-matched against the keys in
`songs.sections`. Examples:

| `song_section` text | Matched key |
|---|---|
| `Verse 1` | `verse_1` |
| `Verse 1 / Pre-Chorus mood` | `verse_1` (first hit) |
| `Pre-Chorus` | `pre_chorus_1` |
| `Chorus` | `chorus_1` |
| `Final Chorus – Lift` | `final_lift` |
| `Bridge` | `bridge` |
| `Drop` | `chorus_1` (synonym) |
| (empty) | `chorus_1` (default) |

If no match works, the worker falls back to `chorus_1` and logs the
mismatch. Future improvement: add a `song_section_override` column on
`production_queue` for manual lookup.

---

## Filename convention

Output filenames are predictable from the song + section + duration:

```
{song_slug}_{section_key}_{N}s.mp3
```

Examples:
- `spring_thaw_verse_1_10s.mp3`
- `spring_thaw_chorus_1_8s.mp3`
- `grand_river_rush_chorus_2_10s.mp3`
- `grand_river_rush_final_lift_10s.mp3`

The slug strips non-alphanumerics and lowercases. Any time you need to
reference a hook in CapCut notes or director-judge prompts, this is the
filename you'll get.

---

## Troubleshooting

**"no matching audio file in 'Roommates - Full Songs' for 'Spring Thaw'"**
The worker tries `audio_drive_filename` first, then fuzzy-matches the song
title against filename stems. If the file is named `spring-thaw-final-mix.mp3`
the slug match should catch it. If not, set the filename explicitly:

```sql
UPDATE public.songs
SET audio_drive_filename = 'spring-thaw-final-mix.mp3'
WHERE song_title = 'Spring Thaw';
```

**"detected: ['chorus_1']" — only one section**
Track was too short or non-rhythmic for librosa's beat tracker. Override
manually with SQL.

**Worker keeps re-processing the same shot**
Check `production_queue.audio_url` — if it's null, the worker treats it
as pending. The worker should populate it after a successful run; if it
didn't, look at the workflow logs for the upload step.

**Apps Script timed out on a big song**
Files >40 MB after base64 encoding (~30 MB raw) may hit the 6-min Apps
Script execution limit. Solutions: lower bitrate, or re-encode the source
to a more compressed format before upload.

**Cost**
Free tier on a private GitHub repo gives 2,000 minutes/month. A typical
run is ~1 minute idle + ~30 sec per song. At one new song every few days,
you'll use < 60 minutes/month.

---

## Migrating off this

To retire the cloud pipeline:
1. Delete `.github/workflows/generate-hooks.yml` from the repo (or push
   an empty commit removing it)
2. Revoke the GitHub secrets

The local `make_hooks.py` keeps working independently — this cloud version
is purely additive.
