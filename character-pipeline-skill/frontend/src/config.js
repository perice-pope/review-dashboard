// ─────────────────────────────────────────────────────────────────────────
// Checkout configuration — point the "Get the skill" buttons at your store.
//
// Easiest: set these as Vercel env vars (Project → Settings → Environment
// Variables), no code edit needed:
//   VITE_CHECKOUT_URL  = https://YOURSTORE.lemonsqueezy.com/buy/xxxxxxxx
//   VITE_PRICE_LABEL   = $29 one-time      (shown next to the button; overrides the default below)
//
// Or just replace the placeholder below and redeploy.
// In Lemon Squeezy: create a product, upload skill-dist/character-pipeline-skill.zip
// as the delivered file, then copy the product's "Buy" / checkout URL here.
// ─────────────────────────────────────────────────────────────────────────

const PLACEHOLDER = 'https://YOURSTORE.lemonsqueezy.com/buy/REPLACE-WITH-YOUR-PRODUCT'

export const CHECKOUT_URL = import.meta.env.VITE_CHECKOUT_URL || PLACEHOLDER
// Default price shown on the buttons until/unless you override it with
// VITE_PRICE_LABEL in Vercel. Change this string to reprice the whole site.
export const PRICE_LABEL = import.meta.env.VITE_PRICE_LABEL || '$29 one-time'

// True once a real store URL is set — lets the UI avoid sending people to a dead link.
export const CHECKOUT_READY = !CHECKOUT_URL.includes('REPLACE-WITH-YOUR-PRODUCT')
