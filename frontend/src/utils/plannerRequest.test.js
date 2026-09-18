import { describe, expect, it } from 'vitest'
import {
  PLANNER_TIMEOUT_MESSAGE,
  createPlannerRequest,
  runPlannerRequest,
} from './plannerRequest'

function abortError() {
  const error = new Error('Aborted')
  error.name = 'AbortError'
  return error
}

describe('runPlannerRequest', () => {
  it('clears the loading flag after a needs_input response', async () => {
    let busy = true
    const request = createPlannerRequest({ timeoutMs: 1000 })
    const outcome = await runPlannerRequest({
      request,
      seq: 1,
      isCurrent: () => true,
      setBusy: (value) => {
        busy = value
      },
      execute: async () => ({
        status: 'needs_input',
        clarification_questions: ['What is your maximum budget?'],
      }),
    })

    expect(outcome.status).toBe('settled')
    expect(outcome.result.status).toBe('needs_input')
    expect(busy).toBe(false)
  })

  it('clears the loading flag after a failed request', async () => {
    let busy = true
    const request = createPlannerRequest({ timeoutMs: 1000 })
    const outcome = await runPlannerRequest({
      request,
      seq: 1,
      isCurrent: () => true,
      setBusy: (value) => {
        busy = value
      },
      execute: async () => {
        throw new Error('Stored travel data is temporarily unavailable.')
      },
    })

    expect(outcome.status).toBe('failed')
    expect(outcome.error.message).toMatch(/unavailable/)
    expect(busy).toBe(false)
  })

  it('clears the loading flag after a malformed response error', async () => {
    let busy = true
    const request = createPlannerRequest({ timeoutMs: 1000 })
    const outcome = await runPlannerRequest({
      request,
      seq: 1,
      isCurrent: () => true,
      setBusy: (value) => {
        busy = value
      },
      execute: async () => {
        throw new Error('The planner returned an unexpected response.')
      },
    })

    expect(outcome.status).toBe('failed')
    expect(busy).toBe(false)
  })

  it('times out, aborts, and clears the loading flag', async () => {
    let busy = true
    const request = createPlannerRequest({ timeoutMs: 20 })
    const outcome = await runPlannerRequest({
      request,
      seq: 1,
      isCurrent: () => true,
      setBusy: (value) => {
        busy = value
      },
      execute: (signal) =>
        new Promise((_, reject) => {
          signal.addEventListener('abort', () => reject(abortError()), { once: true })
        }),
    })

    expect(outcome.status).toBe('aborted')
    expect(outcome.timedOut).toBe(true)
    expect(busy).toBe(false)
    expect(PLANNER_TIMEOUT_MESSAGE).toMatch(/too long/i)
  })

  it('does not clear a newer request’s loading flag when an older request settles', async () => {
    let busy = true
    const request = createPlannerRequest({ timeoutMs: 1000 })
    const outcome = await runPlannerRequest({
      request,
      seq: 1,
      isCurrent: (seq) => seq === 2,
      setBusy: (value) => {
        busy = value
      },
      execute: async () => ({ status: 'needs_input' }),
    })

    expect(outcome.status).toBe('stale')
    expect(busy).toBe(true)
  })
})
