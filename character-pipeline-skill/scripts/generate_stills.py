#!/usr/bin/env python3
"""
generate_stills.py — Stage 2: generate character stills from the trained LoRA.

Runs on the USER'S Replicate token (env: REPLICATE_API_TOKEN). Runs the model
trained in Stage 1 (the fast-flux-trainer output is a runnable FLUX-LoRA model)
to produce one consistent still per prompt.

Golden rules carried through:
  - Every prompt MUST contain the trigger word (we assert it).
  - Stills are downloaded locally immediately — Replicate delivery URLs are
    short-lived (~1h), and Stage 3 (Runway) feeds these files in as the input
    image, so they must exist on disk before the handoff.

Usage:
    python generate_stills.py --lora <model-ref> --trigger cpb_wren_woman \
        --prompts prompts.txt --out ./stills --yes

`--lora` is the trained model reference returned by train_lora.py, e.g.
`username/wren-character` or `username/wren-character:<version>`.
"""
from __future__ import annotations

import sys
import argparse
from pathlib import Path

import replicate  # pip install replicate>=1.0

from _common import (
    replicate_token,
    require_approval,
    is_auth_error,
    download,
)


def _coerce_urls(output) -> list[str]:
    """Normalize replicate.run output into a list of URL strings, whether it
    returns FileOutput objects (default), a single FileOutput, or raw URLs."""
    items = output if isinstance(output, (list, tuple)) else [output]
    urls: list[str] = []
    for it in items:
        if it is None:
            continue
        # FileOutput exposes `.url`; raw outputs are already strings.
        urls.append(getattr(it, "url", None) or str(it))
    return urls


def generate(lora_ref: str, trigger: str, prompts: list[str], out_dir: str,
             *, aspect_ratio: str = "1:1", assume_yes: bool = False) -> list[str]:
    """Generate one image per prompt using the trained LoRA. Returns local file
    paths. Each prompt must already contain the trigger word."""
    replicate_token()  # enforce env var presence; never printed
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    missing = [p for p in prompts if trigger not in p]
    if missing:
        raise ValueError(
            f"{len(missing)} prompt(s) are missing the trigger word '{trigger}'. "
            "Every still prompt must include it or the character won't render. "
            f"First offender: {missing[0][:80]!r}"
        )

    require_approval(
        action=f"Generate {len(prompts)} still(s) on {lora_ref}",
        est_cost="<$1 total on your Replicate account (~20 stills)",
        assume_yes=assume_yes,
    )

    paths: list[str] = []
    for i, prompt in enumerate(prompts, 1):
        print(f"  [{i}/{len(prompts)}] generating…", flush=True)
        try:
            output = replicate.run(
                lora_ref,
                input={
                    "prompt": prompt,            # includes the trigger
                    "num_outputs": 1,
                    "aspect_ratio": aspect_ratio,
                    "output_format": "png",
                    # Push the LoRA at full strength so the trained character
                    # dominates the prompt's scene keywords.
                    "lora_scale": 1.0,
                },
                use_file_output=True,
            )
        except Exception as e:
            if is_auth_error(e):
                sys.exit("Replicate auth failed — check REPLICATE_API_TOKEN. (Key never shown.)")
            raise

        urls = _coerce_urls(output)
        if not urls:
            print(f"  ⚠  prompt {i} produced no output — skipping.", file=sys.stderr)
            continue
        dest = out / f"still_{i:02d}.png"
        # Download immediately — the delivery URL expires within ~1h and Stage 3
        # needs the bytes on disk.
        download(urls[0], dest)
        print(f"        saved {dest}")
        paths.append(str(dest))

    if not paths:
        raise RuntimeError("No stills were produced. Check the LoRA reference and prompts.")
    print(f"\n  ✓ {len(paths)} still(s) saved to {out}/")
    return paths


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Stage 2 — generate stills from the trained LoRA.")
    p.add_argument("--lora", required=True, help="trained model reference from Stage 1")
    p.add_argument("--trigger", required=True, help="trigger word, asserted present in every prompt")
    p.add_argument("--prompts", required=True, help="file with one prompt per line")
    p.add_argument("--out", default="./stills")
    p.add_argument("--aspect", default="1:1", help="aspect ratio, e.g. 1:1, 9:16, 16:9")
    p.add_argument("--yes", action="store_true", help="approve the paid charge (buyer consented)")
    a = p.parse_args()
    prompts = [l.strip() for l in open(a.prompts) if l.strip()]
    if not prompts:
        sys.exit("No prompts found in the prompts file.")
    for path in generate(a.lora, a.trigger, prompts, a.out,
                         aspect_ratio=a.aspect, assume_yes=a.yes):
        print(path)
