// ============================================================
// Plan generation — pure functions. Mirrors the SKILL.md golden
// rules (trigger convention, caption-binding, 15/20-25 counts,
// 1000 steps, 2-LoRA limit + inpainting workaround, animation =
// motion only). No music GENERATION anywhere: audio is only ever a
// scheduling input, never something this pipeline produces.
// ============================================================

export const slug = (s) =>
  (s || '').toLowerCase().replace(/[^a-z0-9]+/g, '').slice(0, 14) || 'char'

export const typeWord = (t) =>
  t === 'man' ? 'man' : t === 'woman' ? 'woman' : 'character'

// cpb_<name>_<type> — unique, non-dictionary trigger.
export const triggerWord = (s) => `cpb_${slug(s.charName)}_${typeWord(s.charType)}`

export const styleText = (s) => s.style || 'your visual style'
export const lookText = (s) => s.charLook || 'their constant features'
export const displayName = (s) => s.charName || 'your character'

// Step 4 — first move branches on the image situation.
export function firstMove(s) {
  if (s.hasImages === 'many')
    return {
      title: 'Train your character model now.',
      note: 'You have enough images. Caption them with the binding rule below, then go straight to training.',
    }
  if (s.hasImages === 'few')
    return {
      title: 'Expand your reference set first, then train.',
      note: 'Use your existing images as a reference to generate a consistent set of 20–25 — same character, varied angles — then train on those.',
    }
  return {
    title: 'Design the character first, then build a reference set.',
    note: 'Lock the look across several angles and outfits before training. Consistency in the training set is everything.',
  }
}

export function trainingSettings() {
  return [
    { k: 'image count', v: '15 floor · **20–25 is the sweet spot** · diminishing returns past 40' },
    { k: 'variety', v: 'same character — vary angle, pose, lighting, distance. Vary everything *except* the constant features.' },
    { k: 'captions', v: 'trigger word + the same constant-features line on every image, then what changes. This binding is what stops drift.' },
    { k: 'steps', v: 'start at 1000. More is not better — too many overfits and the character goes stiff and copy-pasted.' },
    { k: 'base model', v: 'a current Flux-family base trains characters cleanly and stays compatible with the animation step.' },
  ]
}

export function captionTemplate(s) {
  const tw = triggerWord(s)
  const look = lookText(s)
  return (
    `${tw}, ${look}, [what's different in THIS image]\n\n` +
    `Examples:\n` +
    `${tw}, ${look}, sitting at a window, soft morning light, side view\n` +
    `${tw}, ${look}, mid-laugh, close-up, warm indoor lighting\n` +
    `${tw}, ${look}, full body, walking, neon street at night`
  )
}

export function fromIdeaSteps(s) {
  const name = displayName(s)
  const look = lookText(s)
  return [
    `Write a tight visual description of ${name} — the constants only: ${look}.`,
    `Generate a first portrait you love. This is your anchor image.`,
    `Use that anchor as a reference to generate the same character in 20–25 varied poses and angles.`,
    `Caption every image with the template above, then train.`,
  ]
}

// Step 5 — prompt library, trigger filled in. Performance/“instrument”
// stays optional content styling — it is not music generation.
export function promptLibrary(s) {
  const tw = triggerWord(s)
  const look = lookText(s)
  const st = styleText(s)
  return [
    {
      title: 'Still — hero portrait',
      code: `${tw}, ${look}, cinematic portrait, ${st} mood, shallow depth of field, soft key light, [setting]`,
    },
    {
      title: 'Still — performance / in-action',
      code: `${tw}, ${look}, [doing their signature thing], mid-action, expressive, stage lighting, ${st} energy, medium shot`,
    },
    {
      title: 'Still — everyday / "in their world"',
      code: `${tw}, ${look}, [something ordinary — making coffee, on a couch, walking], natural light, candid, relaxed`,
    },
    {
      title: 'Still — wide establishing',
      code: `${tw}, ${look}, full body, [environment], wide shot, [time of day] light`,
    },
    {
      title: 'Animation — feed a still in, describe ONLY the motion',
      note: 'For animation, pass your finished still as the input image and describe movement, not appearance. The image carries the look; the prompt carries the motion.',
      code: `[subtle head bob, fingers moving, slow breathing, hair shifting gently, blinking naturally], locked camera, ${st} tempo`,
    },
  ]
}

export const STATUS_FLOW = 'new  →  audio cut  →  prompts ready  →  review  →  approved  →  published'

export function assetChecklist() {
  return [
    'A folder per character for reference images and the trained model.',
    'A folder for audio — one subfolder per track (audio is an input you cut against, not something this pipeline makes).',
    'A "stills" folder for approved character generations, named by shot.',
    'A "clips" folder for animated output before editing.',
    'One running doc with your trigger word(s), best prompts, and what worked.',
  ]
}

export function shotVariety(s) {
  const look = lookText(s)
  return [
    { b: 'Vary shot length.', t: 'A 30-second short wants ~20 distinct stills, not 4 long holds. Cut on the beat.' },
    { b: 'Use insert shots.', t: `Hands in action, a detail of ${look}, a reaction. Inserts hide seams and add rhythm.` },
    { b: 'Mix distances.', t: 'Close-up → medium → wide. Same character, different framing keeps the eye moving.' },
    { b: 'Real footage collides well.', t: 'If you have any real clips, cutting them next to animation makes both read as more intentional.' },
  ]
}

export function sevenDayPlan(s) {
  const name = displayName(s)
  const day1 =
    s.hasImages === 'none'
      ? `Design ${name}. Generate your anchor portrait and lock the look.`
      : s.hasImages === 'few'
        ? `Generate ${name}'s reference set — get to 20–25 consistent images.`
        : `Caption your ${name} image set using the template, then start the training run.`
  return [
    { day: 'Day 1', title: day1 },
    { day: 'Day 2', title: 'Finish the reference set / training.', note: 'While it trains, set up your asset folders above.' },
    { day: 'Day 3', title: `Test ${name}.`, note: 'Run the hero portrait prompt. Check consistency. Re-caption and retrain if the look drifts.' },
    { day: 'Day 4', title: 'Generate your first batch of stills.', note: 'Aim for ~20 varied shots for one short. Mix close / medium / wide.' },
    { day: 'Day 5', title: 'Animate.', note: 'Feed your best stills in, describe motion only. Build 3–5 short clips.' },
    { day: 'Day 6', title: 'Edit your first short.', note: 'Cut to the beat. Add an insert shot or two. Keep it under 30 seconds.' },
    { day: 'Day 7', title: 'Publish one thing.', note: 'Ship it imperfect. The system improves by running, not by planning.' },
  ]
}

export function audioLine(s) {
  if (s.hasAudio === 'yes') return 'You already have audio — you can go straight to matching visuals to a track.'
  if (s.hasAudio === 'wip') return 'Your audio is in progress — block visuals around the track you finish first.'
  return 'No audio yet — day one can include getting one short piece of audio to cut the first clip against.'
}

export function projectSummary(s) {
  return [
    { k: 'character', v: `${displayName(s)} — ${s.charLook || '—'}` },
    { k: 'trigger word', v: triggerWord(s), mono: true },
    { k: 'style', v: styleText(s) },
    {
      k: 'starting point',
      v:
        (s.hasImages === 'many'
          ? 'training-ready'
          : s.hasImages === 'few'
            ? 'expanding reference set'
            : 'designing from an idea') +
        ' · ' +
        audioLine(s),
    },
  ]
}

// The handoff: a structured brief the buyer pastes into their Claude to run the
// character-pipeline skill. This is the bridge from funnel/intake → skill run.
export function intakeBrief(s) {
  const imgMap = { many: '15+ (training-ready)', few: '1–14 (expand first)', none: 'none (design first)' }
  const techMap = { low: 'keep it simple (web tools only)', mid: 'can follow spelled-out steps', high: 'technical (scripts + API)' }
  const audioMap = { yes: 'ready', wip: 'in progress', no: 'not yet' }
  return [
    `Run the character-pipeline skill for my character.`,
    ``,
    `Character name: ${displayName(s)}`,
    `Type: ${typeWord(s.charType)}`,
    `Constant features (bind these to the trigger): ${lookText(s)}`,
    `Trigger word: ${triggerWord(s)}`,
    `Reference images: ${imgMap[s.hasImages] || 'unknown'}`,
    `Content style: ${styleText(s)}`,
    `Tech comfort: ${techMap[s.tech] || 'unknown'}`,
    `Audio status (scheduling only — do not generate audio): ${audioMap[s.hasAudio] || 'n/a'}`,
    ``,
    `Start at the stage that fits my image situation, keep every paid call gated on my approval, and use my own Replicate + Runway keys.`,
  ].join('\n')
}
