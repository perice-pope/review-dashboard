#!/usr/bin/env python3
"""
train_lora.py — Stage 1: train a character LoRA on Replicate.

Runs on the USER'S Replicate token (env: REPLICATE_API_TOKEN). Wired to
Replicate's `replicate/fast-flux-trainer` (verified mid-2026). Trains a subject
LoRA from a zip of captioned reference images and returns the trained model.

Golden rules enforced by the orchestrator (SKILL.md), passed through here:
  - trigger_word convention  (cpb_<name>_<type>)
  - 15 image floor / 20-25 sweet spot   (checked before zipping, upstream)
  - steps = 1000 default     (more overfits)
  - hand/auto captions live as .txt files inside the zip; we set
    autocaption=False so OUR caption-binding (constants locked to the trigger)
    is what trains, not a fresh auto-caption that would cause drift.

Usage:
    python train_lora.py --images ./set.zip --trigger cpb_wren_woman \
        --destination <username>/<model-name> --yes

    # submit without waiting (poll later):
    python train_lora.py --images ./set.zip --trigger cpb_wren_woman \
        --destination <username>/<model-name> --no-wait --yes

    # check a previously-submitted run:
    python train_lora.py --poll <training-id>
"""
from __future__ import annotations

import sys
import time
import argparse

import replicate  # pip install replicate>=1.0

from _common import (
    replicate_token,
    require_approval,
    status_line,
    is_auth_error,
)

# Trainer + pinned version. fast-flux-trainer "fast" build, verified at
# https://replicate.com/replicate/fast-flux-trainer/train (mid-2026).
# Replicate version ids drift; we pin the known-good short hash and resolve the
# full id at submit time, warning loudly if Replicate has moved past it.
TRAINER = "replicate/fast-flux-trainer"
PINNED_VERSION_PREFIX = "e5a5bc82"  # <- verify/update against the train page

DEFAULT_STEPS = 1000


def resolve_version() -> str:
    """Resolve the full trainer version id, asserting it matches the pinned
    short hash. If Replicate has published a newer version, we surface that
    instead of silently training on an unexpected build."""
    model = replicate.models.get(TRAINER)
    latest = model.latest_version
    if not latest:
        raise RuntimeError(f"{TRAINER} has no published version.")
    full = latest.id
    if not full.startswith(PINNED_VERSION_PREFIX):
        print(
            f"  ⚠  Trainer version drift: pinned {PINNED_VERSION_PREFIX}…, "
            f"Replicate now serves {full[:8]}…. Proceeding with the current "
            f"version. Re-verify the input schema if results look off.",
            file=sys.stderr,
        )
    return f"{TRAINER}:{full}"


def submit(images_zip: str, trigger: str, destination: str, steps: int):
    """Kick off a training run. Returns the replicate Training object."""
    replicate_token()  # enforce env var presence; never printed
    version = resolve_version()
    with open(images_zip, "rb") as zf:
        training = replicate.trainings.create(
            version=version,
            destination=destination,  # an empty Replicate model the user owns
            input={
                "input_images": zf,        # zip: imageN.png + imageN.txt captions
                "trigger_word": trigger,
                "steps": steps,
                "lora_type": "subject",
                # OUR captions are in the zip — do NOT let the trainer re-caption,
                # or the constant-features binding (anti-drift) is thrown away.
                "autocaption": False,
            },
        )
    return training


def poll(training, *, interval: int = 15, timeout: int = 60 * 50):
    """Poll a training to completion, surfacing status. Training runs ~20-30 min;
    we don't block silently — each state change prints state + elapsed."""
    started = time.time()
    last = None
    while training.status not in ("succeeded", "failed", "canceled"):
        if training.status != last:
            status_line("train", training.status, started)
            last = training.status
        if time.time() - started > timeout:
            raise TimeoutError(
                f"Training still {training.status} after {timeout // 60} min — "
                f"check it at the Replicate dashboard (id: {training.id})."
            )
        time.sleep(interval)
        training.reload()
    status_line("train", training.status, started)
    return training


def finish(training) -> str:
    """Validate the terminal state and return the trained model reference."""
    if training.status != "succeeded":
        err = (training.error or "").strip()
        raise RuntimeError(
            f"Training {training.status}: {err or 'no error message returned'}\n"
            "  Drift/overfit? Per SKILL.md, re-check CAPTIONS first — lock the "
            "constant-features string identically across every caption and "
            "retrain BEFORE touching the step count."
        )
    out = training.output
    # fast-flux-trainer returns the trained model/weights reference.
    ref = out.get("version") if isinstance(out, dict) else out
    return ref or training.id


def train(images_zip: str, trigger: str, destination: str, steps: int = DEFAULT_STEPS,
          *, wait: bool = True, assume_yes: bool = False):
    """Submit (after approval) and optionally wait. Returns the trained model
    reference when waiting, or the training id when --no-wait."""
    require_approval(
        action=f"Train LoRA '{trigger}' on {TRAINER} ({steps} steps)",
        est_cost="~$2-4 one-time on your Replicate account",
        assume_yes=assume_yes,
    )
    try:
        training = submit(images_zip, trigger, destination, steps)
    except Exception as e:
        if is_auth_error(e):
            sys.exit("Replicate auth failed — check REPLICATE_API_TOKEN. (Key never shown.)")
        raise
    print(f"  Training submitted. id={training.id}")
    print(f"  Watch it live: https://replicate.com/p/{training.id}")
    if not wait:
        print("  (--no-wait) Re-run with --poll", training.id, "to check status.")
        return training.id
    training = poll(training)
    ref = finish(training)
    print(f"\n  ✓ Trained. Your character model: {ref}")
    print(f"    See it on Replicate: https://replicate.com/{destination}")
    return ref


def poll_existing(training_id: str):
    replicate_token()
    training = replicate.trainings.get(training_id)
    training = poll(training)
    ref = finish(training)
    print(f"\n  ✓ Trained. Your character model: {ref}")
    return ref


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Stage 1 — train a character LoRA on Replicate.")
    p.add_argument("--images", help="path to the captioned image zip")
    p.add_argument("--trigger", help="trigger word, e.g. cpb_wren_woman")
    p.add_argument("--destination", help="<username>/<model-name> on Replicate (must exist, empty)")
    p.add_argument("--steps", type=int, default=DEFAULT_STEPS)
    p.add_argument("--no-wait", action="store_true", help="submit and return the id without polling")
    p.add_argument("--poll", metavar="TRAINING_ID", help="poll a previously-submitted training")
    p.add_argument("--yes", action="store_true", help="approve the paid charge (buyer consented)")
    a = p.parse_args()

    if a.poll:
        poll_existing(a.poll)
    else:
        if not (a.images and a.trigger and a.destination):
            p.error("--images, --trigger and --destination are required (or use --poll)")
        print(train(a.images, a.trigger, a.destination, a.steps,
                    wait=not a.no_wait, assume_yes=a.yes))
