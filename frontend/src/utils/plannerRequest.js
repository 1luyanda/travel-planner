/**
 * Abort + timeout + busy-flag lifecycle for POST /api/recommend and /api/refine.
 * Loading/refining must be cleared in `finally` for the current request generation,
 * including needs_input, error, abort, timeout, and malformed responses.
 * Enrichment is not part of this helper so map lookups cannot keep the spinner up.
 */

export const PLANNER_REQUEST_TIMEOUT_MS = 120_000

export const PLANNER_TIMEOUT_MESSAGE =
  'The planner took too long to respond. Please try again.'

export function createPlannerRequest({ timeoutMs = PLANNER_REQUEST_TIMEOUT_MS } = {}) {
  const controller = new AbortController()
  const timeoutId = setTimeout(() => {
    if (!controller.signal.aborted) controller.abort()
  }, timeoutMs)

  return {
    controller,
    signal: controller.signal,
    abort() {
      controller.abort()
    },
    dispose() {
      clearTimeout(timeoutId)
    },
  }
}

/**
 * @param {object} options
 * @param {{ signal: AbortSignal, dispose: () => void }} options.request
 * @param {number} options.seq
 * @param {(seq: number) => boolean} options.isCurrent
 * @param {(busy: boolean) => void} options.setBusy
 * @param {(signal: AbortSignal) => Promise<unknown>} options.execute
 */
export async function runPlannerRequest({ request, seq, isCurrent, setBusy, execute }) {
  try {
    const result = await execute(request.signal)
    return { status: isCurrent(seq) ? 'settled' : 'stale', result }
  } catch (error) {
    const aborted = error?.name === 'AbortError'
    const current = isCurrent(seq)
    return {
      status: current ? (aborted ? 'aborted' : 'failed') : 'stale',
      error,
      aborted,
      timedOut: aborted && current,
    }
  } finally {
    request.dispose()
    if (isCurrent(seq)) setBusy(false)
  }
}
