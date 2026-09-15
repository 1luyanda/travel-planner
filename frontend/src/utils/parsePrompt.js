const TRAVEL_HINTS =
  /\b(warm|hot|beach|cool|cold|budget|cheap|afford|under|direct|stop|short|relax|getaway|trip|flight|flights|destination|origin|airport|travel|weather|rain|holiday|vacation|escape|price|prefer|euro|eur)\b|€/i

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

function parseBudget(text) {
  const match =
    text.match(/(?:under|below|max(?:imum)?|up to|<=?)\s*€?\s*(\d{2,5})/i) ||
    text.match(/€\s*(\d{2,5})/) ||
    text.match(/(\d{2,5})\s*(?:€|eur|euro)/i)
  return match ? Number(match[1]) : null
}

/**
 * Deterministic demo parser. Not an LLM.
 * Understands budget, warmth, direct flights, short travel, origin codes, and known cities.
 */
export function parsePrompt(text, { origins = [], cities = [] } = {}) {
  const raw = text.trim()
  if (!raw) {
    return { ok: false, message: 'Type a trip request, or pick a starter prompt.' }
  }

  const origin = origins.find((code) => new RegExp(`\\b${escapeRegExp(code)}\\b`, 'i').test(raw)) || ''
  const city = cities.find((name) => new RegExp(`\\b${escapeRegExp(name)}\\b`, 'i').test(raw)) || ''
  const hasTravel = TRAVEL_HINTS.test(raw) || Boolean(origin) || Boolean(city)

  if (!hasTravel) {
    return {
      ok: false,
      message:
        'This demo only understands trip requests about budget, warmth, direct flights, and short getaways. It is not an LLM. Try one of the starter prompts.',
    }
  }

  const preferWarm = /\b(warm|hot|beach)\b/i.test(raw) && !/\b(cool|cold)\b/i.test(raw)
  const filters = {
    mood: raw,
    origin,
    maxBudget: parseBudget(raw) ?? 400,
    directOnly: /\bdirect\b/i.test(raw),
    preferWarm,
  }

  if (/\b(cool|cold)\b/i.test(raw)) filters.preferWarm = false

  let refinement = null
  if (/\bshort\b/i.test(raw)) refinement = 'Shorter travel'
  else if (/\bdirect\b/i.test(raw)) refinement = 'Direct flights'
  else if (/\b(cheap|cheaper|afford)/i.test(raw) && !filters.preferWarm) refinement = 'Cheaper'

  return { ok: true, filters, refinement, city }
}
