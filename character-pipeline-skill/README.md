# Character Pipeline — Claude Skill

The production pipeline behind The Roommates, packaged as a Claude skill that
builds the buyer's own animated character end to end.

**Runs on the buyer's own API keys.** Train → stills → animate, fully automated,
fewest manual steps. The skill orchestrates; the buyer's Replicate and Runway
accounts do the compute. No hosted backend, no per-user cost to the seller.

## Structure
```
SKILL.md                      orchestration brain — the full guided flow
scripts/
  _common.py                  shared helpers: key handling, approval gate, handoff
  train_lora.py               Stage 1 — Replicate fast-flux-trainer (wired)
  generate_stills.py          Stage 2 — Replicate stills from the LoRA (wired)
  animate.py                  Stage 3 — Runway image-to-video (wired)
  requirements.txt            replicate>=1.0, runwayml>=5.0
references/
  captioning.md               the caption logic that prevents drift
  prompt-library.md           still + motion prompts
  expand-set.md               handling <15 or zero reference images
frontend/                     React intake wizard (Roommates-branded funnel)
.env.example                  copy to .env; keys live ONLY in the environment
```

## Status
Wired. The three scripts call the live APIs (Replicate `fast-flux-trainer` +
trained-LoRA inference, Runway `image_to_video`), with async polling, the
Replicate→Runway handoff (still downloaded, fed to Runway as a base64 data URI),
a paid-action approval gate (`--yes`), env-only key handling, and the SKILL.md
failure handling. See the "Running the wired scripts" section of `SKILL.md`.

> Live paid runs require the buyer's own `REPLICATE_API_TOKEN` and
> `RUNWAY_API_KEY` set in the environment — no keys are bundled. The trainer
> version is pinned (short hash `e5a5bc82`) and re-resolved to the full id at
> submit time, warning on drift.

## Keys (buyer sets locally — never committed, never printed)
```
REPLICATE_API_TOKEN=...
RUNWAY_API_KEY=...
```
