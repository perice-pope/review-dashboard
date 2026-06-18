#!/usr/bin/env python3
"""
animate.py — Stage 3: animate stills into clips on Runway (image-to-video).

Runs on the USER'S Runway key (env: RUNWAY_API_KEY; RUNWAYML_API_SECRET also
accepted). Wired to the official `runwayml` SDK (>=5.x, verified mid-2026).

Models (mid-2026):
  - gen4_turbo : cheapest, ~5 credits/sec ($0.01/credit) — default, good for iteration
  - gen4.5     : best quality, costs more

THE CROSS-PLATFORM HANDOFF (the risky part this script proves):
  The still lives on Replicate; Runway has to animate it. Rather than hand
  Runway a short-lived Replicate URL (which can expire or be refused), Stage 2
  already downloaded the still to disk, and we feed Runway the bytes inline as a
  base64 data URI (see _common.prompt_image_for_runway). An http(s) URL is still
  accepted and passes through unchanged.

Golden rule: animation = MOTION ONLY. The still carries the look; prompt_text
describes movement, never appearance.

Usage:
    python animate.py --image ./stills/still_01.png \
        --motion "subtle head bob, slow breathing, natural blinking, locked camera" \
        --model gen4_turbo --duration 5 --ratio 720:1280 --out ./clips --yes
"""
from __future__ import annotations

import sys
import time
import argparse
from pathlib import Path

from runwayml import RunwayML  # pip install runwayml>=5

from _common import (
    runway_key,
    require_approval,
    status_line,
    is_auth_error,
    prompt_image_for_runway,
    download,
)

# Friendly name -> Runway model string.
MODELS = {
    "gen4_turbo": "gen4_turbo",   # cheapest, good for iteration
    "gen4_5":     "gen4.5",       # best quality, costs more
    "gen4.5":     "gen4.5",
}

# Per-second credit cost (1 credit = $0.01) for the rough estimate we show.
_CREDITS_PER_SEC = {"gen4_turbo": 5, "gen4.5": 12}

# Runway image_to_video accepts a fixed set of ratios; default to vertical.
DEFAULT_RATIO = "720:1280"


def _client() -> RunwayML:
    # Pass the key explicitly so we honor RUNWAY_API_KEY (the SDK's own default
    # env var is RUNWAYML_API_SECRET). The key is never printed.
    return RunwayML(api_key=runway_key())


def _est_cost(model: str, duration: int) -> str:
    per = _CREDITS_PER_SEC.get(model, 5)
    credits = per * duration
    return f"~{credits} credits (~${credits * 0.01:.2f}) on your Runway account"


def _submit(client: RunwayML, image_uri: str, motion: str, model: str,
            duration: int, ratio: str) -> str:
    task = client.image_to_video.create(
        model=model,
        prompt_image=image_uri,   # the still carries the look
        prompt_text=motion,       # MOTION ONLY
        duration=duration,
        ratio=ratio,
    )
    return task.id


def _poll(client: RunwayML, task_id: str, *, interval: int = 10,
          timeout: int = 60 * 15) -> dict:
    """Poll a Runway task to completion, surfacing status (non-blocking-style
    ticks). Runway statuses: PENDING / THROTTLED / RUNNING / SUCCEEDED / FAILED."""
    started = time.time()
    last = None
    while True:
        task = client.tasks.retrieve(task_id)
        state = task.status
        if state != last:
            status_line("animate", state, started)
            last = state
        if state == "SUCCEEDED":
            out = task.output
            return {"output": list(out) if out else []}
        if state in ("FAILED", "CANCELLED"):
            reason = getattr(task, "failure", None) or getattr(task, "failure_reason", None) or state
            raise RuntimeError(f"Runway job {state}: {reason}")
        if time.time() - started > timeout:
            raise TimeoutError(f"Runway task {task_id} stuck in {state} after {timeout // 60} min.")
        time.sleep(interval)


def animate(image: str, motion: str, model: str = "gen4_turbo", duration: int = 5,
            out_dir: str = "./clips", ratio: str = DEFAULT_RATIO,
            *, assume_yes: bool = False) -> str:
    """Animate a single still. The still is fed in as the input image; `motion`
    describes movement only. Retries once on a Runway failure (per SKILL.md),
    then surfaces the error. Returns the local clip path."""
    model_str = MODELS.get(model, "gen4_turbo")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    require_approval(
        action=f"Animate {Path(image).name} on Runway {model_str}, {duration}s",
        est_cost=_est_cost(model_str, duration),
        assume_yes=assume_yes,
    )

    # The handoff: local still -> base64 data URI Runway accepts. Resolved BEFORE
    # any retry so a missing/expired source fails loudly and early.
    image_uri = prompt_image_for_runway(image)

    client = _client()
    last_err: Exception | None = None
    for attempt in (1, 2):  # initial try + one retry, per SKILL.md
        try:
            if attempt == 2:
                print("  Runway failed once — retrying.", file=sys.stderr)
            task_id = _submit(client, image_uri, motion, model_str, duration, ratio)
            print(f"  Runway task submitted. id={task_id}")
            result = _poll(client, task_id)
            urls = result["output"]
            if not urls:
                raise RuntimeError("Runway succeeded but returned no output URL.")
            dest = out / f"{Path(image).stem}.mp4"
            download(urls[0], dest, timeout=300)
            print(f"\n  ✓ Clip saved: {dest}")
            return str(dest)
        except Exception as e:
            if is_auth_error(e):
                sys.exit("Runway auth failed — check RUNWAY_API_KEY. (Key never shown.)")
            last_err = e
            print(f"  attempt {attempt} failed: {e}", file=sys.stderr)

    # Both attempts failed — surface Runway's error verbatim and stop.
    raise RuntimeError(f"Runway animation failed twice; surfacing the error:\n  {last_err}")


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Stage 3 — animate a still on Runway (image-to-video).")
    p.add_argument("--image", required=True, help="local still path (preferred) or http(s) URL")
    p.add_argument("--motion", required=True, help="MOVEMENT only, not appearance")
    p.add_argument("--model", default="gen4_turbo", choices=list(MODELS.keys()))
    p.add_argument("--duration", type=int, default=5, choices=[5, 10], help="clip length in seconds")
    p.add_argument("--ratio", default=DEFAULT_RATIO, help="e.g. 720:1280, 1280:720, 960:960")
    p.add_argument("--out", default="./clips")
    p.add_argument("--yes", action="store_true", help="approve the paid charge (buyer consented)")
    a = p.parse_args()
    print(animate(a.image, a.motion, a.model, a.duration, a.out, a.ratio, assume_yes=a.yes))
