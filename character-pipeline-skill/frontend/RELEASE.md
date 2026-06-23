# Release playbook — selling the Character Pipeline skill

This is the seller-side guide (future-you). It is **not** shipped to buyers — it
lives in `frontend/`, which is never included in the skill zip.

The model: the **website is free** (the 6-step planner is the lead magnet). The
**skill zip is the paid product**, delivered by Lemon Squeezy after checkout. The
zip is **never** served from the site.

There are two independent things you ship:
- **A)** The **skill zip** → uploaded to Lemon Squeezy as the digital file.
- **B)** The **website** → deployed on Vercel, with the checkout URL in an env var.

Do A whenever the skill content changes. Do B whenever the site or the checkout
URL changes. They don't depend on each other.

---

## A) Build the skill zip and upload it to Lemon Squeezy

### 1. Build the zip
From `frontend/`:
```bash
npm install            # first time only
npm run pack:skill
```
This writes **`frontend/skill-dist/character-pipeline-skill.zip`**. That folder is
gitignored and is **never** part of the website build — it exists only so you can
hand the file to Lemon Squeezy.

What's inside the zip (curated allowlist in `scripts/pack-skill.mjs`): `START_HERE.md`,
`SKILL.md`, `README.md`, `.env.example`, and the `scripts/` + `references/`
folders — extracting to a clean `character-pipeline/` folder. It never includes
the website, secrets, or generated assets.

> Sanity check before uploading: `unzip -l skill-dist/character-pipeline-skill.zip`
> — confirm you see `character-pipeline/START_HERE.md` and `scripts/`, and that
> there is **no** `.env`, no `frontend/`, and no images.

### 2. Create / update the Lemon Squeezy product
In your Lemon Squeezy dashboard:
1. **Products → New Product** (or open the existing one).
2. Type: **Digital product / single payment**. Set the price (the site shows
   `$29 one-time` by default — keep them in sync, see B).
3. Under **Files**, upload `character-pipeline-skill.zip` as the delivered file.
   On a later release, **replace** the file here and re-publish — buyers get the
   new version on their next download; the checkout URL stays the same.
4. Make sure **delivery = Lemon Squeezy file delivery** (the buyer gets a
   download link by email + on the success page). Publish the product.

### 3. Grab the checkout URL
On the product, copy its **Buy / checkout URL**. It looks like:
```
https://YOURSTORE.lemonsqueezy.com/buy/XXXXXXXX-XXXX-XXXX
```
You'll paste this into the website env var in section B.

### 4. Test purchase ($0.50)
Create a **separate $0.50 test product** with the same zip and run a real
purchase end-to-end (use your own card or LS test mode). Confirm:
- Checkout opens (as an overlay if `lemon.js` loaded, else a new tab).
- After paying, you receive the **download link** and the zip downloads.
- Unzipping gives the `character-pipeline/` folder with `START_HERE.md` on top.

Delete or unpublish the $0.50 product when done.

---

## B) Deploy the website with the checkout URL wired in

The site reads two env vars at **build time** (Vite — they must be present when
Vercel builds, and they must start with `VITE_`):

| Env var | What it does | Example |
|---|---|---|
| `VITE_CHECKOUT_URL` | Where every "Get the skill" button points | `https://YOURSTORE.lemonsqueezy.com/buy/XXXXXXXX` |
| `VITE_PRICE_LABEL`  | Price shown on the buttons (optional; overrides the `$29 one-time` default in `src/config.js`) | `$29 one-time` |

Until `VITE_CHECKOUT_URL` is set to a real URL, the buttons fall back to a visible
placeholder and the Lemon Squeezy overlay stays off (so you never ship a dead
overlay link). `CHECKOUT_READY` in `src/config.js` is the flag that gates this.

### Set them in Vercel and redeploy
1. Vercel → your project → **Settings → Environment Variables**.
2. Add `VITE_CHECKOUT_URL` (the URL from A3) for **Production** (and Preview if
   you want previews live). Optionally add `VITE_PRICE_LABEL`.
3. **Redeploy** so the new env vars are baked into the build:
   - Push to the deployed branch, **or**
   - Vercel → **Deployments → ⋯ → Redeploy** on the latest one.
4. Load the site and click any **Get the skill** button → it should open your
   Lemon Squeezy checkout (overlay or new tab). The price should read what you set.

> Changing the checkout URL or price later = update the env var in Vercel and
> redeploy. No code change needed. To change the *default* price in code (shown
> before any env var is set), edit `PRICE_LABEL` in `src/config.js`.

### Local preview of the wired-up site (optional)
```bash
VITE_CHECKOUT_URL="https://YOURSTORE.lemonsqueezy.com/buy/XXXX" npm run build && npm run preview
```

---

## Guardrails (don't undo these)

- **Never** add a `prebuild` hook that runs `pack:skill`, and never move the zip
  into `public/` or `dist/`. That would serve the paid product for free. The zip
  must only ever live in the gitignored `skill-dist/`.
- The website build is just `vite build` (see `vercel.json`) — it does **not**
  build the zip. That separation is intentional.
- `.env` (real keys) and `skill-dist/` are gitignored. Keep them that way.

## One-glance checklist for a new release
- [ ] `npm run pack:skill` → new `skill-dist/character-pipeline-skill.zip`
- [ ] `unzip -l` sanity check (has `START_HERE.md` + `scripts/`, no `.env`)
- [ ] Replace the file on the Lemon Squeezy product, re-publish
- [ ] (If URL/price changed) update Vercel env vars + redeploy
- [ ] Click a "Get the skill" button on the live site → checkout opens
