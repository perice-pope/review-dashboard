import React, { useEffect, useMemo, useRef, useState } from 'react'
import {
  RichText, CodeBlock, Panel, KV, Checklist, Callout,
  OptionCard, Field, Stepmap, CopyButton,
} from './components.jsx'
import * as P from './data/plan.js'
import { CHECKOUT_URL, PRICE_LABEL, CHECKOUT_READY } from './config.js'

// "Get the skill" → Lemon Squeezy checkout. With a real store URL, lemon.js opens
// it as an overlay (class hook); until then it's a plain link to the placeholder.
function GetSkillButton({ variant = 'primary' }) {
  const cls = `btn btn-${variant}${CHECKOUT_READY ? ' lemonsqueezy-button' : ''}`
  return (
    <a className={cls} href={CHECKOUT_URL} target="_blank" rel="noopener noreferrer">
      Get the skill{PRICE_LABEL ? ` — ${PRICE_LABEL}` : ''} →
    </a>
  )
}

const STEP_LABELS = ['Character', 'Assets', 'Setup', 'Model', 'Prompts', 'Launch']
const TOTAL = 6

const INITIAL = {
  charName: '', charType: '', charLook: '',
  hasImages: '', hasAudio: '',
  tech: '', style: '',
}

export default function App() {
  const [s, setS] = useState(INITIAL)
  const [cur, setCur] = useState(0) // 0 = hero, 1..6 = steps
  const [error, setError] = useState('')
  const stageRef = useRef(null)
  const topRef = useRef(null)

  const set = (k, v) => setS((prev) => ({ ...prev, [k]: v }))

  useEffect(() => {
    if (cur > 0) topRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }, [cur])

  function validate(step) {
    if (step === 1) {
      if (!s.charName.trim()) return 'enter a character name'
      if (!s.charType) return 'pick a character type'
    }
    if (step === 2) {
      if (!s.hasImages) return 'pick your image situation'
      if (!s.hasAudio) return 'pick your audio situation'
    }
    if (step === 3 && !s.tech) return 'pick a comfort level'
    return ''
  }

  function next() {
    const err = validate(cur)
    if (err) { setError(err); return }
    setError('')
    if (cur < TOTAL) setCur(cur + 1)
  }
  function prev() { setError(''); if (cur > 1) setCur(cur - 1) }
  function begin() { setCur(1); setTimeout(() => stageRef.current?.scrollIntoView({ behavior: 'smooth' }), 0) }
  function restart() { setS(INITIAL); setCur(0); setError(''); window.scrollTo({ top: 0, behavior: 'smooth' }) }

  return (
    <>
      <header className="bar">
        <div className="bar-inner">
          <a className="wordmark" href="#" onClick={(e) => { e.preventDefault(); restart() }}>
            <span className="mark" aria-hidden>◓</span>
            <span className="wm-name">THE ROOMMATES</span>
            <small>character pipeline</small>
          </a>
          {cur > 0 && (
            <div className="progress-mini">STEP <b>{cur}</b> / {TOTAL}</div>
          )}
        </div>
        <div className="track"><div className="track-fill" style={{ width: `${(cur / TOTAL) * 100}%` }} /></div>
      </header>

      <span ref={topRef} />
      <div className="shell">
        {cur === 0 && <Hero onBegin={begin} labels={STEP_LABELS} />}

        {cur > 0 && (
          <section className="stage" ref={stageRef}>
            <Stepmap labels={STEP_LABELS} current={cur} />

            <div className="step" key={cur}>
              {cur === 1 && <StepCharacter s={s} set={set} />}
              {cur === 2 && <StepAssets s={s} set={set} />}
              {cur === 3 && <StepSetup s={s} set={set} />}
              {cur === 4 && <StepTrain s={s} />}
              {cur === 5 && <StepPrompts s={s} />}
              {cur === 6 && <StepLaunch s={s} onRestart={restart} />}

              <div className="nav">
                <span className="note" style={error ? { color: 'var(--copper)' } : undefined}>
                  {error || `step ${cur} of ${TOTAL}${cur === TOTAL ? ' — done' : ''}`}
                </span>
                <div className="nav-btns">
                  {cur > 1 && <button className="btn btn-ghost" onClick={prev}>← Back</button>}
                  {cur < TOTAL
                    ? <button className="btn btn-primary" onClick={next}>{cur === 3 ? 'Build my plan →' : 'Continue →'}</button>
                    : <button className="btn btn-ghost" onClick={() => window.print()}>Save / print plan</button>}
                </div>
              </div>
            </div>
          </section>
        )}

        <footer>
          THE ROOMMATES · Character Pipeline — the production pipeline behind the brand, packaged as a Claude skill.<br />
          Runs on your own Replicate + Runway keys. Your inputs never leave your browser; the skill never stores your keys or files.
        </footer>
      </div>
    </>
  )
}

/* ── Hero ─────────────────────────────────────────────────────────────── */
function Hero({ onBegin, labels }) {
  return (
    <section className="hero">
      <div className="eyebrow">REVEAL · the pipeline behind The Roommates</div>
      <h1>Build your character.<br /><span className="thin">We hand you the whole pipeline.</span></h1>
      <p className="lede">
        This is the exact production system behind The Roommates — train a consistent character,
        generate stills, animate them. Answer a few questions and we’ll generate your trigger word,
        a training plan tuned to what you have, a prompt library, and your first week. Then the
        Claude skill runs the train → stills → animate pass on your own keys.
      </p>
      <div className="start-row">
        <button className="btn btn-primary" onClick={onBegin}>Start building →</button>
        <GetSkillButton variant="ghost" />
        <span className="meta">~6 minutes · nothing leaves your browser</span>
      </div>
      <p className="meta">
        Checkout delivers the skill plus a step-by-step setup guide — works with Claude Code or Claude Desktop, runs on your own keys.
      </p>
      <div className="value-row">
        <Value k="Train" v="A character LoRA on Replicate — captioned to stay consistent." cost="~$2–4 one-time" />
        <Value k="Stills" v="A batch of on-model stills from your trained character." cost="under $1 / ~20" />
        <Value k="Animate" v="Short clips on Runway — your still in, motion out." cost="~$0.05–0.12 / sec" />
      </div>
      <Stepmap labels={labels} current={0} />
    </section>
  )
}
function Value({ k, v, cost }) {
  return (
    <div className="value">
      <div className="value-k">{k}</div>
      <div className="value-v">{v}</div>
      <div className="value-cost">{cost} · your spend, on your keys</div>
    </div>
  )
}

/* ── Step 1 — Character ───────────────────────────────────────────────── */
function StepCharacter({ s, set }) {
  return (
    <>
      <StepHead n="01" title="Your character" sub="Start with one character. You’ll add the rest later with the same system — but the whole pipeline is easier to learn with a single character first." />
      <Field label="Character name" hint="Short and distinct. This becomes part of your model’s trigger word, so avoid common dictionary words.">
        <input type="text" value={s.charName} onChange={(e) => set('charName', e.target.value)} placeholder="e.g. Maya, Kofi, Wren, Sol" autoComplete="off" />
      </Field>
      <Field label="What kind of character is this?" hint="Used to build your trigger word and caption template correctly.">
        <div className="opts three">
          <OptionCard selected={s.charType === 'woman'} title="Woman" onClick={() => set('charType', 'woman')} />
          <OptionCard selected={s.charType === 'man'} title="Man" onClick={() => set('charType', 'man')} />
          <OptionCard selected={s.charType === 'creature'} title="Stylized / creature" desc="non-human or heavily stylized" onClick={() => set('charType', 'creature')} />
        </div>
      </Field>
      <Field label="Describe their look in one line" hint="The constant features that should never change — these get bound to the trigger word so the model locks them in.">
        <input type="text" value={s.charLook} onChange={(e) => set('charLook', e.target.value)} placeholder="e.g. teal locs, gold septum ring, oversized denim jacket" autoComplete="off" />
      </Field>
    </>
  )
}

/* ── Step 2 — Assets ──────────────────────────────────────────────────── */
function StepAssets({ s, set }) {
  return (
    <>
      <StepHead n="02" title="What you’ve got so far" sub="Your starting assets decide your first move. There’s a path whether you have artwork ready or you’re starting from nothing." />
      <Field label="Do you have reference images of this character?">
        <div className="opts">
          <OptionCard selected={s.hasImages === 'many'} title="Yes — 15 or more" desc="enough to train a character model now" onClick={() => set('hasImages', 'many')} />
          <OptionCard selected={s.hasImages === 'few'} title="A handful (1–14)" desc="enough to generate more from" onClick={() => set('hasImages', 'few')} />
          <OptionCard selected={s.hasImages === 'none'} title="None yet — just an idea" desc="we’ll start by designing the character" onClick={() => set('hasImages', 'none')} />
        </div>
      </Field>
      <Field label="Do you have audio ready to cut against?" hint="Scheduling only — this pipeline animates characters, it doesn’t generate audio. We just use this to sequence your week.">
        <div className="opts three">
          <OptionCard selected={s.hasAudio === 'yes'} title="Yes — ready" onClick={() => set('hasAudio', 'yes')} />
          <OptionCard selected={s.hasAudio === 'wip'} title="In progress" onClick={() => set('hasAudio', 'wip')} />
          <OptionCard selected={s.hasAudio === 'no'} title="Not yet" onClick={() => set('hasAudio', 'no')} />
        </div>
      </Field>
    </>
  )
}

/* ── Step 3 — Setup ───────────────────────────────────────────────────── */
function StepSetup({ s, set }) {
  return (
    <>
      <StepHead n="03" title="Your setup" sub="This tunes how much hand-holding the generated guide gives you, and which tools it points you at." />
      <Field label="How comfortable are you with technical tools?">
        <div className="opts">
          <OptionCard selected={s.tech === 'low'} title="Keep it simple" desc="web tools only, no code, no command line" onClick={() => set('tech', 'low')} />
          <OptionCard selected={s.tech === 'mid'} title="I can follow steps" desc="happy to paste commands if they’re spelled out" onClick={() => set('tech', 'mid')} />
          <OptionCard selected={s.tech === 'high'} title="I’m technical" desc="give me the scripts and the API route" onClick={() => set('tech', 'high')} />
        </div>
      </Field>
      <Field label="What’s your content style?" hint="Shapes your prompt library’s mood and the shot types you’ll get.">
        <input type="text" value={s.style} onChange={(e) => set('style', e.target.value)} placeholder="e.g. cozy lo-fi, neon synthpop, warm flat illustration" autoComplete="off" />
      </Field>
    </>
  )
}

/* ── Step 4 — Training plan ───────────────────────────────────────────── */
function StepTrain({ s }) {
  const tw = P.triggerWord(s)
  const fm = P.firstMove(s)
  return (
    <>
      <StepHead n="04" title="Your model training plan" sub="This is the part most people get wrong. Follow it exactly and your character stays consistent across every generation." />
      <Panel accent kicker="Your first move" kickerNote="based on what you have">
        <div className="big">{fm.title}</div>
        <div className="dim">{fm.note}</div>
      </Panel>

      <Panel kicker="Your trigger word">
        <p className="dim mb">The unique word that summons your character. Use it in every prompt. It’s deliberately not a real word so the model can’t confuse it with anything else.</p>
        <CodeBlock>{tw}</CodeBlock>
        <Callout>
          The caption rule that makes or breaks consistency: in <b>every</b> training caption, attach the
          constant features to the trigger word — <b>“{tw}, {P.lookText(s)}, [pose/scene that changes]”</b> —
          and never describe those constants as if they vary. Let auto-captioning re-describe the hair or
          outfit each time and the model learns them as variable, so your character drifts.
        </Callout>
      </Panel>

      <Panel kicker="Training settings that work">
        <KV rows={P.trainingSettings()} />
      </Panel>

      <Panel kicker="Caption template" kickerNote="copy this format for every image">
        <CodeBlock>{P.captionTemplate(s)}</CodeBlock>
      </Panel>

      {s.hasImages === 'none' && (
        <Panel kicker="Since you’re starting from an idea">
          <Checklist items={P.fromIdeaSteps(s)} mark={(i) => i + 1} />
        </Panel>
      )}

      {s.tech === 'high' && (
        <Panel kicker="Technical note" kickerNote="since you’re comfortable with code">
          <p className="dim mb">The skill drives this for you with <code>scripts/train_lora.py</code>. Under the hood it zips your captioned set and kicks off a hosted training run — pinned version, 1000 steps, your trigger word, custom captions (no auto-caption):</p>
          <CodeBlock>{`python scripts/train_lora.py \\
  --images ${P.slug(s.charName)}_set.zip \\
  --trigger ${tw} \\
  --destination <your-username>/${P.slug(s.charName)}-character \\
  --yes   # only after you approve the ~$2–4 charge`}</CodeBlock>
        </Panel>
      )}
    </>
  )
}

/* ── Step 5 — Prompt library ──────────────────────────────────────────── */
function StepPrompts({ s }) {
  return (
    <>
      <StepHead n="05" title="Your prompt library" sub="Copy-paste ready, with your character’s trigger word already filled in. These are starting points — tune the bracketed parts." />
      <Panel accent kicker="The multi-character rule" kickerNote="read this first">
        <p>
          Quality falls apart when you stack more than two character models in one generation. To put
          several characters in one scene, build it up <b>one character at a time</b> with inpainting —
          place character one, lock it, inpaint character two into the same frame, and so on. Then animate
          the finished composite still. Don’t fight the stacking limit; work around it.
        </p>
      </Panel>

      {P.promptLibrary(s).map((p, i) => (
        <Panel key={i} kicker={p.title}>
          {p.note && <p className="dim mb">{p.note}</p>}
          <CodeBlock>{p.code}</CodeBlock>
        </Panel>
      ))}

      <Panel kicker="Shot variety" kickerNote="so it doesn’t feel AI-generic">
        <Checklist items={P.shotVariety(s)} />
      </Panel>
    </>
  )
}

/* ── Step 6 — Launch + handoff ────────────────────────────────────────── */
function StepLaunch({ s, onRestart }) {
  const brief = useMemo(() => P.intakeBrief(s), [s])
  return (
    <>
      <StepHead n="06" title="Your build plan" sub="Your asset checklist, your production status flow, the next seven days — and the brief that hands all of this to the skill." />

      <Panel accent kicker="Your project at a glance">
        <KV rows={P.projectSummary(s)} />
      </Panel>

      <Panel brass kicker="Hand off to the skill" kickerNote="this is how you actually run it">
        <p className="dim mb">
          Copy this brief and paste it into your Claude with the Character Pipeline skill installed. It runs
          train → stills → animate on <b>your own</b> Replicate + Runway keys, and stops for your approval
          before every paid call.
        </p>
        <div className="codeblock">
          <CopyButton getText={brief} label="copy brief" />
          <code>{brief}</code>
        </div>
        <p className="dim mb" style={{ marginTop: 14 }}>
          Don’t have the skill yet?{' '}
          <a href={CHECKOUT_URL} className={CHECKOUT_READY ? 'lemonsqueezy-button' : undefined} target="_blank" rel="noopener noreferrer">Get the Character Pipeline skill</a>
          {' '}— it ships with a step-by-step setup guide for Claude Code or Desktop.
        </p>
      </Panel>

      <Panel kicker="Asset checklist" kickerNote="set this up once">
        <Checklist items={P.assetChecklist()} mark="☐" />
      </Panel>

      <Panel kicker="Production status flow" kickerNote="how a piece moves to published">
        <p className="dim mb">Track every video through these six states. Knowing exactly where each piece sits is what lets you scale past one-offs.</p>
        <CodeBlock copy={false}>{P.STATUS_FLOW}</CodeBlock>
        <Callout>When you bring on help later, scope them to <b>review</b> and <b>community</b> only at first — keep generation in your hands until the system is stable.</Callout>
      </Panel>

      <Panel kicker="Your next 7 days">
        <div className="daygrid">
          {P.sevenDayPlan(s).map((d, i) => (
            <div className="day" key={i}>
              <div className="dn">{d.day}</div>
              <div className="dt"><b>{d.title}</b>{d.note && <span><RichText text={d.note} /></span>}</div>
            </div>
          ))}
        </div>
      </Panel>

      <Panel kicker="You’re set up">
        <p className="dim">
          You have {P.displayName(s)}’s trigger word, a training plan tuned to what you have, a prompt
          library, an asset structure, a status flow, and a week mapped out. Save this page (print → save as
          PDF), then paste your brief into Claude and run Day 1.
        </p>
        <div className="outro-actions">
          <button className="btn btn-ghost" onClick={onRestart}>Start over</button>
        </div>
      </Panel>
    </>
  )
}

/* ── shared ───────────────────────────────────────────────────────────── */
function StepHead({ n, title, sub }) {
  return (
    <>
      <div className="step-head"><span className="step-num">{n}</span><h2>{title}</h2></div>
      <p className="sub">{sub}</p>
    </>
  )
}
