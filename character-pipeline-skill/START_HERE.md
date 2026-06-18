# Start Here — Character Pipeline

Thanks for buying the **Character Pipeline** skill. It's the exact system behind
The Roommates: train a consistent character, generate stills of it, and animate
them into short clips — guided start to finish by Claude.

You're reading this because you just unzipped the bundle. Here's everything you
need, in order. It takes about 15 minutes to set up.

---

## What you need first

1. **Claude with Skills** — either:
   - **Claude Code** (the terminal app), or
   - **Claude Desktop** (the Mac/Windows app) with the **Skills** feature.
2. **Two API accounts** (you'll create these — they're what pay for the AI compute):
   - **Replicate** → for training your character + making stills
   - **Runway** → for animating
3. **~20 reference images** of your character (15 minimum), same character across
   varied angles, poses, and lighting.
4. **Python 3** installed (for the pipeline scripts).

> You pay Replicate and Runway directly, on your own keys. Rough costs: training
> **~$2–4 once**, stills **under $1** for ~20, animation **~$0.05–0.12 per second**.
> Nothing in this bundle ever sees or stores your keys.

---

## Step 1 — Unzip

You should have a folder named **`character-pipeline`** containing `SKILL.md`,
`scripts/`, `references/`, and this file. Keep the folder together.

## Step 2 — Install the skill into Claude

**If you use Claude Code (terminal):**
Move the `character-pipeline` folder into your Claude skills folder so the path
looks like this:
```
~/.claude/skills/character-pipeline/SKILL.md
```
On Mac/Linux you can do that with:
```
mkdir -p ~/.claude/skills && mv character-pipeline ~/.claude/skills/
```

**If you use Claude Desktop (app):**
Open **Settings → Capabilities → Skills**, choose **Add skill**, and point it at
this `character-pipeline` folder. (Follow the in-app prompts — the app copies the
folder in for you.)

## Step 3 — Get your two API keys

- **Replicate token:** https://replicate.com/account/api-tokens
- **Runway key:** https://dev.runwayml.com (developer portal)

Then make a copy of `.env.example` named `.env` and paste your keys in:
```
REPLICATE_API_TOKEN=your_replicate_token_here
RUNWAY_API_KEY=your_runway_key_here
```
Keep `.env` private — never share or upload it.

## Step 4 — Install the pipeline's Python tools

From inside the folder:
```
pip install -r character-pipeline/scripts/requirements.txt
```
(If you used Claude Code in Step 2, the folder is at
`~/.claude/skills/character-pipeline/`.)

## Step 5 — Run it

Open Claude and say:
```
Use the character-pipeline skill to build my character.
```
Claude takes over from there — it asks for your reference images, builds your
character's trigger word and training plan, and runs **train → stills → animate**
for you. It pauses for your OK before anything that costs money.

> **Tip:** if you came from the website wizard, paste the **brief** it generated
> for you instead — it pre-fills your character details so Claude can move faster.

---

## Quick troubleshooting

- **"Claude doesn't see the skill."** Double-check the folder location (Step 2) and
  restart Claude. The file `SKILL.md` must sit directly inside the
  `character-pipeline` folder.
- **"Authentication / 401 from Replicate or Runway."** Your key isn't loaded —
  re-check `.env` (Step 3) and that you saved it in the same folder you run from.
- **"Not enough images."** See `references/expand-set.md` — it covers how to get to
  a usable set from just a few images, or from a single idea.

That's it — you're set up. Build your first character and go.
