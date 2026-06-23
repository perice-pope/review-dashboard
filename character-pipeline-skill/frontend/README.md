# Character Pipeline — Intake Wizard (React)

The Roommates-branded funnel + intake wizard. Markets the Character Pipeline
skill and collects the buyer's character details, then generates a personalized
plan and a **handoff brief** to paste into Claude to run the skill.

This is a React rebuild of `../wizard-frontend.html`. Same 6-step flow and
generated plan, re-skinned in the Roommates identity (copper/brass on teal-navy,
Fraunces display). All **music-generation framing removed** — audio is kept only
as a scheduling input, never something this pipeline produces.

## Run it

```bash
npm install
npm run dev        # http://localhost:5173
npm run build      # production build → dist/
npm run preview    # serve the build
npm run pack:skill # build the PAID skill zip → skill-dist/ (gitignored, never served)
```

## Selling it

The site is the free lead magnet; the **skill zip is the paid product**, delivered
by Lemon Squeezy. To build the zip, upload it to Lemon Squeezy, and wire the
checkout URL into the site, follow **[RELEASE.md](./RELEASE.md)** — the full
seller playbook (build → upload → set `VITE_CHECKOUT_URL` in Vercel → redeploy →
test purchase). The checkout URL and price come from env vars; see `src/config.js`.

## Flow

1. **Character** — name, type, constant features (→ trigger word).
2. **Assets** — reference images (15+/1–14/none) + audio status (scheduling only).
3. **Setup** — tech comfort + content style.
4. **Model plan** *(generated)* — trigger word, caption-binding rule, training
   settings, caption template; **branches on the image situation**.
5. **Prompt library** *(generated)* — stills + motion prompts with the trigger
   filled in; multi-character / 2-LoRA rule.
6. **Build plan** *(generated)* — asset checklist, six-state status flow, 7-day
   plan, and the **intake brief** that hands off to the skill.

## Structure

```
src/
  App.jsx            wizard state + the 6 steps + generated output
  components.jsx     presentational pieces (Panel, OptionCard, CodeBlock, …)
  data/plan.js       pure plan-generation logic (mirrors SKILL.md golden rules)
  styles/theme.css   Roommates design tokens (brand palette + type)
  styles/app.css     component styles
```

The wizard runs entirely client-side — nothing is sent anywhere, and it never
touches API keys. The skill (one directory up) does the actual paid work on the
buyer's own Replicate + Runway accounts.
