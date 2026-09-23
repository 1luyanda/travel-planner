import { useEffect, useRef } from 'react'

/** Fraction of the scroll viewport's height where the "reading line" sits. */
const FOCUS_LINE = 0.4
const SETTLE_MS = 200

/**
 * Pick the mapped card (marked with data-map-kind/data-map-key) whose centre is
 * nearest the reading line of the visible scroll viewport. Cards inside a
 * collapsed section or scrolled out of view are skipped.
 */
export function pickFocusedCard(root, view) {
  const line = view.top + (view.bottom - view.top) * FOCUS_LINE
  let best = null
  let bestDistance = Infinity
  for (const card of root.querySelectorAll('[data-map-key]')) {
    if (card.closest('[hidden]')) continue
    const rect = card.getBoundingClientRect()
    if (!rect.height || rect.bottom <= view.top || rect.top >= view.bottom) continue
    const distance = Math.abs((rect.top + rect.bottom) / 2 - line)
    if (distance < bestDistance) {
      best = card
      bestDistance = distance
    }
  }
  return best
}

function viewportOf(scroller) {
  if (scroller === document.documentElement || scroller === document.body) {
    return { top: 0, bottom: window.innerHeight }
  }
  const rect = scroller.getBoundingClientRect()
  return { top: rect.top, bottom: rect.bottom }
}

/**
 * When the user scrolls whatever contains `rootRef`, report the card under the
 * reading line once scrolling settles, so the map can follow the list.
 */
export function useScrollMapFocus(rootRef, onFocus) {
  const onFocusRef = useRef(onFocus)
  onFocusRef.current = onFocus

  useEffect(() => {
    let timer
    // Scroll events do not bubble, so listen in the capture phase for any scroller.
    const handle = (event) => {
      const root = rootRef.current
      const scroller = event.target === document ? document.documentElement : event.target
      if (!root || !(scroller instanceof Element) || !scroller.contains(root)) return
      window.clearTimeout(timer)
      timer = window.setTimeout(() => {
        const card = pickFocusedCard(root, viewportOf(scroller))
        if (card) onFocusRef.current?.(card.dataset.mapKind, card.dataset.mapKey)
      }, SETTLE_MS)
    }
    document.addEventListener('scroll', handle, true)
    return () => {
      document.removeEventListener('scroll', handle, true)
      window.clearTimeout(timer)
    }
  }, [rootRef])
}
