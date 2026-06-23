# Start Here — Character Pipeline

Thanks for buying the **Character Pipeline** skill. It's the exact system behind
The Roommates: train a consistent character, generate stills of it, and animate
them into short clips — guided start to finish by Claude.

This guide gets you from a fresh unzip to your **first generated still and a
5-second animation in about an hour**. Follow it top to bottom. Every command is
written out — you only ever copy and paste.

**Two phases:**
- **Day 0 — Setup (~15 min):** install the skill, get two API keys, install the tools.
- **Day 1 — First run (~30–45 min, mostly waiting):** run the skill on a sample
  character, watch it train, get stills, animate one.

---

## What you need first

1. **Claude with Skills** — either:
   - **Claude Code** (the terminal app), or
   - **Claude Desktop** (the Mac/Windows app) with the **Skills** feature.
2. **Two API accounts** (you'll create these — they're what pay for the AI compute):
   - **Replicate** → training your character + making stills
   - **Runway** → animating
3. **Python 3.9+** installed (for the pipeline scripts). Check with `python3 --version`.
4. *(Optional for Day 1)* ~20 reference images of your own character. The Day 1
   walkthrough below uses a **sample character built from a description**, so you
   can do your first full run without any images of your own.

> You pay Replicate and Runway directly, on your own keys. Rough costs for a
> first run: training **~$2–4 once**, ~20 stills **under $1**, one 5-second
> animation **~$0.25–0.60**. Nothing in this bundle ever sees or stores your keys.

---

# Day 0 — Setup

## Step 1 — Unzip

You should have a folder named **`character-pipeline`** containing `SKILL.md`,
`scripts/`, `references/`, `.env.example`, and this file. Keep the folder together.

## Step 2 — Install the skill into Claude

**If you use Claude Code (terminal):**
Move the `character-pipeline` folder into your Claude skills folder so the path
looks like this:
```
~/.claude/skills/character-pipeline/SKILL.md
```
On Mac/Linux:
```
mkdir -p ~/.claude/skills && mv character-pipeline ~/.claude/skills/
```

**If you use Claude Desktop (app):**
Open **Settings → Capabilities → Skills**, choose **Add skill**, and point it at
this `character-pipeline` folder. The app copies the folder in for you.

**Confirm it loaded:** start Claude and ask *"What skills do you have?"* —
`character-pipeline` should be in the list. If it isn't, see Troubleshooting →
*"Claude doesn't see the skill."*

## Step 3 — Get your two API keys

- **Replicate token:** **https://replicate.com/account/api-tokens** → *Create token*
- **Runway key:** **https://dev.runwayml.com** → log in → *API Keys* → create one

You'll also need a little credit on each account (a few dollars on Replicate, a
small Runway credit pack) — see the cost note above.

## Step 4 — Make your keys visible to the skill

The scripts read your keys **only from environment variables** — they never read
a file on their own and never store anything. So you have to load them into your
shell. From inside the skill folder:

```bash
cp .env.example .env        # then open .env and paste your two keys in
set -a && source .env && set +a   # loads them into the current shell
```

Your `.env` should look like:
```
REPLICATE_API_TOKEN=r8_your_real_token
RUNWAY_API_KEY=key_your_real_key
```

> **Important:** keys are loaded **per shell session**. Run the `source` line in
> the same terminal where you launch **Claude Code**, *before* you start it — the
> skill inherits your environment. If you start Claude first, quit it, `source`,
> and relaunch. For **Claude Desktop**, set the keys as system environment
> variables (or run the `source` step in the terminal Desktop uses for tools),
> then restart the app. Keep `.env` private — it's gitignored; never share it.

Quick check (won't reveal the key — just confirms it's set):
```bash
[ -n "$REPLICATE_API_TOKEN" ] && echo "Replicate key: set" || echo "Replicate key: MISSING"
[ -n "$RUNWAY_API_KEY" ] && echo "Runway key: set" || echo "Runway key: MISSING"
```

## Step 5 — Install the pipeline's Python tools

From inside the skill folder:
```bash
pip install -r scripts/requirements.txt
```
(If you installed via Claude Code in Step 2, the folder is at
`~/.claude/skills/character-pipeline/`, so:
`pip install -r ~/.claude/skills/character-pipeline/scripts/requirements.txt`.)

You're set up. On to your first run.

---

# Day 1 — Your first run

## Step 6 — Run the skill on a sample character

You don't need your own images for this first pass. Open Claude and paste this
**exactly** — it tells the skill to invent a sample character and run the whole
pipeline on it:

```
Use the character-pipeline skill. I don't have my own images yet — build a
SAMPLE character so I can see the full pipeline end to end. Use: a woman with
teal locs and a gold septum ring, cozy lo-fi style. Walk me through it:
generate a reference set, train the LoRA, make ~20 stills, then animate one
still into a 5-second clip. Pause and ask me before any paid step.
```

Claude takes over from here. It will:
1. Propose a **trigger word** (e.g. `cpb_sample_woman`) and a caption plan.
2. Build a small reference set from the description (since you have no images).
3. **Pause for your approval** before the paid training call — this is the
   ~$2–4 charge. Say *yes* to proceed.
4. Train the LoRA, then generate stills, then animate one — pausing before each
   paid step.

> Want to use your **own** character instead? Skip the sample line and say
> *"Use the character-pipeline skill to build my character — I have ~20 reference
> images in this folder: <path>."* If you came from the website planner, paste
> the **brief** it generated for you; it pre-fills everything.

## Step 7 — What success looks like at each stage

**Training (Stage 1) — ~20–30 min.** Claude submits the job and polls it. You'll
see a submit line, a live link, then status ticks until it's done:
```
  Training submitted. id=abcd1234
  Watch it live: https://replicate.com/p/abcd1234
  [train] processing  04:30 elapsed
  [train] succeeded   22:10 elapsed
  ✓ Trained. Your character model: <your-username>/sample-character
    See it on Replicate: https://replicate.com/<your-username>/sample-character
```
Open that Replicate link — that's your character, now reusable forever.

**Stills (Stage 2) — ~1–3 min, under $1.** Claude generates a batch (~20) using
the trained model, with your trigger word in every prompt. It saves them locally
(a `stills/` folder) and shows you a link. **This is your first generated
still** — open the folder and look. They should all clearly be the *same*
character.

**Animation (Stage 3) — ~1–2 min, ~$0.25–0.60 for 5s.** Pick one still you like.
Claude sends it to Runway with a **motion-only** prompt (e.g. *"subtle head bob,
slow breathing, natural blinking, locked camera"*) and returns a `.mp4` in a
`clips/` folder. Play it — that's your animated character.

If you reached a playable clip, the whole pipeline works. From here, swap in your
own images and real prompts.

---

## Troubleshooting — the things that actually break

**1. "Out of Replicate credits" / billing error during training or stills.**
Training won't start (or stills fail) if your Replicate balance is empty. Top up
at **https://replicate.com/account/billing**, then re-run the step. A first run
needs only a few dollars.

**2. "Runway model not found" / `400 invalid_value` on the animation step.**
Runway renames its video models over time. The skill ships with these valid
model names (pass via `--model`):
- **`gen4_turbo`** — default, cheapest (~5 credits/sec ≈ $0.05/sec)
- **`gen4.5`** — higher quality, costs more (~12 credits/sec)

If Runway rejects both with `invalid_value`, the model id has changed on their
end. Find the **current** image-to-video model id in Runway's API docs
(**https://docs.dev.runwayml.com** → image-to-video), then update the `MODELS`
map near the top of `scripts/animate.py` to include it — or just tell Claude
*"Runway says invalid_value for the model; check the current model name and
update animate.py."* It'll do it.

**3. "Keys not picked up" / `REPLICATE_API_TOKEN is not set` / `401` / auth error.**
The skill only reads keys from the environment of the shell it runs in. Re-run
Step 4's `source` line **in the same terminal you launched Claude from**, then
restart Claude. Confirm with the quick check in Step 4. The most common cause is
loading the keys in one terminal and running Claude in another.

**4. "Character drifts off-model" — stills don't look like the same person.**
Drift is almost always a **captioning** problem, not a training-steps problem.
The fix:
- Every training caption must read: `<trigger>, <constant features>, <what
  changes in this image>`. The constant features (hair, signature item, defining
  marks) go in **every** caption, bound to the trigger word.
- Never let the constants get re-described as if they vary (e.g. don't caption
  the hair color differently per image) — that teaches the model they're optional.
- Re-caption and **retrain** before touching the step count. More steps makes
  drift worse, not better (it overfits). See `references/captioning.md`.
- Too few/too similar images also causes drift — aim for 20–25 varied shots.

---

## Where to get help

Stuck on something this guide doesn't cover? Email **themeadowcorp@gmail.com** —
include which step you're on and the exact error text (never your API keys).
We aim to reply within 48 hours.

That's it — you're set up. Build your first character and go.
