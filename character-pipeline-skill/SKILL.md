---
name: character-pipeline
description: >
  Builds a consistent AI-animated character end to end: trains a character LoRA
  from the user's reference images, generates a set of stills of that character,
  then animates those stills into short clips. Use when the user wants to create
  an animated character, "build my character," train a character model/LoRA, make
  a character consistent across shots, or turn character art into animated video.
  Runs entirely on the USER'S OWN API keys (Replicate + Runway) — this skill
  orchestrates their accounts, it does not provide compute.
---

# Character Pipeline

> The exact production pipeline behind The Roommates — now it builds yours.
> Train a consistent character, generate stills, animate. One guided run.

## What this skill does

This skill walks the user through the full character-creation pipeline and makes
the API calls for them at each stage, checking in only when it needs a decision
or an asset. Three stages:

1. **Train** — a character LoRA on Replicate from the user's reference images.
2. **Stills** — a batch of consistent character images using the trained LoRA.
3. **Animate** — short clips on Runway, using the stills as input frames.

Everything runs on the **user's own Replicate and Runway API keys**. This skill
never holds keys, never fronts compute, never stores the user's files anywhere
except their own accounts and their local machine.

## Before you start — required from the user

Collect these once, at the top of the run. Do NOT proceed past Stage 1 setup
until all three are confirmed.

- **Replicate API token** — used for training + stills. Get it at replicate.com/account/api-tokens
- **Runway API key** — used for animation. Get it in the Runway developer portal.
- **Reference images** — 15 minimum, 20–25 is the sweet spot. Same character,
  varied angles/poses/lighting, consistent core features.

Read keys from environment variables the user sets locally. NEVER print a key
back to the user, NEVER write a key to any file, NEVER include a key in a prompt
or a log line.

```
REPLICATE_API_TOKEN=...
RUNWAY_API_KEY=...
```

## The golden rules (carry these through every stage)

These are the hard-won lessons baked into this pipeline. Apply them; don't
let the user skip them.

- **Trigger word.** Build a unique, non-dictionary trigger: `cpb_<name>_<type>`
  (e.g. `cpb_wren_woman`). Use it in every caption and every prompt.
- **Captions bind the constants.** Every training caption is:
  `<trigger>, <constant features>, <what changes in THIS image>`.
  The constant features (hair, signature clothing, defining marks) go in EVERY
  caption attached to the trigger, so the model locks them. Never let the
  constants get described as if they vary — that is what causes character drift.
- **Image count.** 15 floor, 20–25 sweet spot, diminishing returns past 40.
- **Steps.** Default 1000. More is not better; over-training overfits and the
  character comes out stiff and copy-pasted.
- **Multi-character limit.** Never stack more than 2 LoRAs in one generation.
  For multiple characters in one frame, build it up one character at a time with
  inpainting, then animate the finished composite still.
- **Animation = motion only.** When animating, pass the still as the input image
  and describe ONLY the motion. The image carries the look; the prompt carries
  the movement.

## Stage 1 — Train the character LoRA

1. Confirm the user's reference images are accessible locally and count >= 15.
   If fewer than 15, route to `references/expand-set.md` before training.
2. Derive the trigger word from the character's name + type.
3. Auto-caption every image using the caption template in the golden rules.
   Write captions to matching `.txt` files (image1.png -> image1.txt).
   Show the user 2–3 sample captions and let them correct the constant-features
   line once; apply that correction across all captions.
4. Zip the captioned image set.
5. Call `scripts/train_lora.py` (Replicate fast-flux-trainer). Pass the zip,
   the trigger word, steps=1000, lora_type=subject.
6. Training takes ~20–30 min. Poll status. Tell the user it's running and what
   to expect; don't block waiting silently.
7. On success, give the user the link to their trained model on Replicate.
   "Here's your character — you can see it at this link."

See `scripts/train_lora.py` for the call. See `references/captioning.md` for the
captioning logic.

## Stage 2 — Generate stills

1. Load the prompt library from `references/prompt-library.md`. Fill the trigger
   word into each prompt.
2. Ask the user what they want: hero portrait, performance shot, everyday/in-world,
   or a custom scene. Default to a varied batch of ~20 if they just say "make stills."
3. Call `scripts/generate_stills.py` (Replicate, the trained LoRA). Generate the
   batch. Save outputs locally and to the user's Replicate account.
4. Show the user the results link. "Here are your stills."
5. Let them pick which stills move forward to animation.

## Stage 3 — Animate

1. For each chosen still, ask for (or infer) a motion description — movement only.
2. Call `scripts/animate.py` (Runway image-to-video, Gen-4 Turbo default for cost,
   Gen-4.5 if the user asks for max quality). Pass the still as the input image
   and the motion prompt.
3. Runway runs async — poll, don't block. Save finished clips locally.
4. Show the user the clips link. "Here are your animated clips."

Cost note to surface to the user once, before Stage 3: animation is the part that
costs the most on their Runway account (~$0.05–0.12 per second depending on model).
Let them choose model + clip length with that in mind. This is THEIR spend.

## Failure handling

- **Bad training result (drift / overfit):** re-check captions first — drift is
  almost always a captioning problem, not a steps problem. Re-caption the
  constants and retrain before touching step count.
- **Auth error:** the key is wrong or unset. Point the user to set the env var.
  Never echo the key.
- **Runway job fails:** retry once; if it fails again, surface Runway's error
  verbatim and pause for the user.

## What to NEVER do

- Never print, log, or write the user's API keys.
- Never run a generation the user didn't approve — every paid call is their money.
- Never claim a stage succeeded without confirming the API response.

## Running the wired scripts

The three scripts are wired to live APIs (Replicate `fast-flux-trainer` + stills,
Runway `image_to_video`). Install once: `pip install -r scripts/requirements.txt`.
Keys come from the environment only (`REPLICATE_API_TOKEN`, `RUNWAY_API_KEY`).

Every script **refuses to spend money without approval**. Once the user has
explicitly approved a charge in the conversation, pass `--yes` so the call runs;
without it the script prompts (interactive) or refuses (non-interactive).

```bash
# Stage 1 — train (~20-30 min, ~$2-4 one-time). Captions live as .txt in the zip.
python scripts/train_lora.py --images set.zip --trigger cpb_wren_woman \
    --destination <user>/wren-character --yes
#   --no-wait to submit and return the id;  --poll <id> to check later.

# Stage 2 — stills (<$1 for ~20). Every prompt must contain the trigger word.
python scripts/generate_stills.py --lora <user>/wren-character \
    --trigger cpb_wren_woman --prompts prompts.txt --out ./stills --yes

# Stage 3 — animate (~$0.05-0.12/sec). The Replicate->Runway handoff feeds the
# downloaded still to Runway as a base64 data URI (no expiring cross-host URL).
python scripts/animate.py --image ./stills/still_01.png \
    --motion "subtle head bob, slow breathing, natural blinking, locked camera" \
    --model gen4_turbo --duration 5 --ratio 720:1280 --out ./clips --yes
```

The trainer version is pinned (short hash) and re-resolved to the full id at
submit time; if Replicate has moved past the pinned build, the script warns
rather than training silently on an unexpected version.
