"""
assets.py — Single source of truth for character and setting reference images.

To add a new image:

    1. Drop the PNG/JPG into a publicly-shared Google Drive folder.
       Get the file ID from the share URL:
           https://drive.google.com/file/d/<FILE_ID>/view
       OR upload it to Runway's asset library and grab the asset UUID.

    2. Add one line to CHARACTERS or SCENES below:
           "MyChar":  drive("FILE_ID"),     # Drive
           "MyChar":  runway("UUID"),       # Runway
           "MyChar":  "https://..."         # any HTTPS URL also works

    3. That's it — both the runner and the dashboard pick it up next run.

Naming rules:
    • Character keys are CapitalizedNames (Peter, Maya, ...). Prompts reference
      them as @Peter / @Maya. The runner lowercases the tag automatically when
      sending to Runway.
    • Scene keys are snake_case slugs (kitchen_morning, hallway_night, ...).
      Prompts reference them as @kitchen_morning. The slug IS the tag.

Reference cap: Runway accepts at most 3 referenceImages per text_to_image call.
The runner prioritizes characters over scenes when there are more than 3 refs.
"""


def drive(file_id: str) -> str:
    """Public Google Drive image URL (returns raw image bytes for shared files)."""
    return f"https://lh3.googleusercontent.com/d/{file_id}=s2048"


def runway_upload(upload_id: str) -> str:
    """
    Runway upload URI from POST /v1/uploads. Format is `runway://upload/<id>`.
    Note: the older `runway://asset/<uuid>` form is no longer accepted by
    referenceImages — the Runway API only takes https://, runway://upload/…,
    or data:image/… URIs. If you have legacy asset UUIDs, re-host the image
    on Drive (or re-upload via /v1/uploads).
    """
    return f"runway://upload/{upload_id}"


# ─────────────────────────────────────────────────────────────────────────────
#  CHARACTERS — keys are CapitalizedNames; tags in prompts use @CapName
# ─────────────────────────────────────────────────────────────────────────────
CHARACTERS: dict[str, str] = {
    "Peter":  drive("1QEmdr63x-PtQfXI8KrhFp2U1akodiW_M"),
    "Marcus": drive("17wlhVnXclHswTqkUoBAIWL8lyMit-qH9"),
    "Julian": drive("1qaBCNVuPDejC-PR6s_xGSW8prA7pAMlw"),
    "Noah":   drive("12GiLteJSpiKZ9ReMGY1GnWl5IF5XOQeg"),
    "Maya":   drive("1MhfH14NUxrUH40ToepBcjZyzW6i9jPCK"),
}


# ─────────────────────────────────────────────────────────────────────────────
#  SCENES — keys are snake_case slugs; tags in prompts use @slug verbatim
#
#  Empty by default — drop your setting PNGs into a public Drive folder, grab
#  each file ID, and add a line. Example:
#       "kitchen_morning":   drive("1AbC2dEfGhIjKlMnOpQrStUvWxYz0123456"),
#       "living_room_day":   drive("1XyZ..."),
#
#  Older `runway://asset/<uuid>` URIs from the legacy run_batch.py SCENES dict
#  are NOT compatible with the current referenceImages API — re-upload via
#  Drive or POST /v1/uploads if you want to use them.
# ─────────────────────────────────────────────────────────────────────────────
SCENES: dict[str, str] = {
    # "kitchen_morning": drive("PUT_FILE_ID_HERE"),
}


def all_character_names() -> list[str]:
    return list(CHARACTERS.keys())


def all_scene_tags() -> list[str]:
    return list(SCENES.keys())


def lookup_character(name: str) -> str | None:
    """Case-insensitive lookup by display name."""
    if not name:
        return None
    target = name.strip().lower()
    for key, uri in CHARACTERS.items():
        if key.lower() == target:
            return uri
    return None


def lookup_scene(tag: str) -> str | None:
    """Exact match on snake_case slug."""
    if not tag:
        return None
    return SCENES.get(tag.strip())


# ─────────────────────────────────────────────────────────────────────────────
#  CHARACTER_LORAS — Replicate-trained LoRA per character (still generation)
#
#  After training a LoRA on Replicate (see runner/training.md or the VA pilot
#  guide), drop the model identifier here. Format:
#
#      "Maya": {
#          "lora": "perice-pope/maya-roommates",   # Replicate model id
#          "version": "abc123…",                   # specific version hash, optional
#          "trigger": "MAYA_RM",                   # the prompt token that summons her
#      }
#
#  Leave `lora` as None until that character is trained — the runner falls back
#  to the manual-keyframe path (status=needs_keyframe) for any shot that uses a
#  character whose LoRA isn't ready.
#
#  Trigger words go in prompts as plain ALL-CAPS tokens (NO @ symbol). The
#  runner translates the existing @maya/@noah tags in runway_prompt to the
#  trigger words before submitting to Replicate.
# ─────────────────────────────────────────────────────────────────────────────
# Optional `extra_input` dict per character — merged into the Replicate input
# payload so you can tune knobs like num_inference_steps or guidance without
# touching the runner. FLUX-dev LoRAs typically accept ~28 steps + guidance 3.5;
# FLUX-schnell-derived LoRAs cap steps at 4. The runner falls back to the
# model's published defaults when extra_input is empty/missing.
CHARACTER_LORAS: dict[str, dict] = {
    "Peter":  {"lora": None, "version": None, "trigger": "PETER_RM", "extra_input": {}},
    "Marcus": {"lora": None, "version": None, "trigger": "MARCUS_RM", "extra_input": {}},
    "Julian": {"lora": None, "version": None, "trigger": "JULIAN_RM", "extra_input": {}},
    "Noah":   {"lora": None, "version": None, "trigger": "NOAH_RM", "extra_input": {}},
    "Maya":   {"lora": None, "version": None, "trigger": "MAYA_RM", "extra_input": {}},
}


def lookup_lora(name: str) -> dict | None:
    """Case-insensitive lookup. Returns None if name unknown OR LoRA not trained."""
    if not name:
        return None
    target = name.strip().lower()
    for key, val in CHARACTER_LORAS.items():
        if key.lower() == target and val.get("lora"):
            return val
    return None


def all_loras_ready(names: list[str]) -> tuple[bool, list[str]]:
    """Return (all_ready, missing_names) for a list of character names."""
    missing = []
    for n in names:
        if not lookup_lora(n):
            missing.append(n)
    return (not missing, missing)


# ─────────────────────────────────────────────────────────────────────────────
#  INSERT_MODEL — Replicate model used for shots without characters
#  (insert/establishing/match_cut). Pure prompt → still, no character LoRAs.
#
#  Default points at the public flux-schnell (cheap, fast, ~$0.003/image). Once
#  you train a Roommates STYLE LoRA, swap in here so inserts match the show's
#  visual language without burning a character LoRA slot.
# ─────────────────────────────────────────────────────────────────────────────
INSERT_MODEL: dict = {
    "lora": "black-forest-labs/flux-schnell",
    "version": None,
    "trigger": "",                        # no trigger word for insert/style
    "extra_input": {"num_inference_steps": 4},   # flux-schnell cap
}
