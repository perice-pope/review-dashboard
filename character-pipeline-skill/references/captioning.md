# Captioning logic

The single most important step. Get this wrong and the character drifts.

## The format

Every caption, for every training image, follows:

```
<trigger>, <constant features>, <what is different in THIS image>
```

- `<trigger>` — the unique word, e.g. `cpb_wren_woman`. Always first.
- `<constant features>` — the things that NEVER change about the character:
  hair, signature clothing, defining marks. These go in EVERY caption so the
  model binds them to the trigger. This is what keeps the character consistent.
- `<what is different>` — pose, angle, expression, setting, lighting, framing.
  This is the only part that varies caption to caption.

## Examples

```
cpb_wren_woman, teal locs, gold septum ring, denim jacket, sitting at a window, soft morning light, side view
cpb_wren_woman, teal locs, gold septum ring, denim jacket, mid-laugh, close-up, warm indoor light
cpb_wren_woman, teal locs, gold septum ring, denim jacket, full body, walking, neon street at night
```

## The trap to avoid

Auto-captioners describe the hair and clothes fresh every time, often slightly
differently ("blue dreadlocks" / "teal braids" / "green hair"). The model then
learns those features as *variable*, and the character drifts across generations.

Fix: lock ONE constant-features string and paste it identically into every
caption. Let the user confirm/correct that one string once, then apply it to all.

## Workflow in the skill

1. Generate a first-pass caption per image (auto is fine for the "what's different"
   part).
2. Insert the fixed `<trigger>, <constant features>,` prefix on every one.
3. Show the user 2–3 samples, let them fix the constant-features string once.
4. Re-apply across all captions. Write `imageN.txt` next to each `imageN.png`.
5. Zip images + captions together for training.
