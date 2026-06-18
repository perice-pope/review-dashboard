// ─────────────────────────────────────────────────────────────────────────
// Checkout configuration — point the "Get the skill" buttons at your store.
//
// Easiest: set these as Vercel env vars (Project → Settings → Environment
// Variables), no code edit needed:
//   VITE_CHECKOUT_URL  = https://YOURSTORE.lemonsqueezy.com/buy/xxxxxxxx
//   VITE_PRICE_LABEL   = $29 one-time      (optional; shown next to the button)
//
// Or just replace the placeholder below and redeploy.
// In Lemon Squeezy: create a product, upload skill-dist/character-pipeline-skill.zip
// as the delivered file, then copy the product's "Buy" / checkout URL here.
// ─────────────────────────────────────────────────────────────────────────

const PLACEHOLDER = 'https://YOURSTORE.lemonsqueezy.com/buy/REPLACE-WITH-YOUR-PRODUCT'

export const CHECKOUT_URL = import.meta.env.VITE_CHECKOUT_URL || PLACEHOLDER
export const PRICE_LABEL = import.meta.env.VITE_PRICE_LABEL || ''

// True once a real store URL is set — lets the UI avoid sending people to a dead link.
export const CHECKOUT_READY = !CHECKOUT_URL.includes('REPLACE-WITH-YOUR-PRODUCT')
