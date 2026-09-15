import { describe, expect, it } from 'vitest'
import { parsePrompt } from './parsePrompt'

describe('parsePrompt', () => {
  it('parses the warm budget starter', () => {
    const result = parsePrompt('A warm escape under €400')
    expect(result.ok).toBe(true)
    expect(result.filters.preferWarm).toBe(true)
    expect(result.filters.maxBudget).toBe(400)
    expect(result.filters.directOnly).toBe(false)
  })

  it('parses affordable direct flights', () => {
    const result = parsePrompt('Show me affordable direct flights')
    expect(result.ok).toBe(true)
    expect(result.filters.directOnly).toBe(true)
    expect(result.refinement).toBe('Direct flights')
  })

  it('applies shorter-travel refinement for short getaways', () => {
    const result = parsePrompt('A short, relaxing getaway')
    expect(result.ok).toBe(true)
    expect(result.refinement).toBe('Shorter travel')
  })

  it('rejects unrelated text instead of pretending to understand it', () => {
    const result = parsePrompt('What is the capital of Mars?')
    expect(result.ok).toBe(false)
    expect(result.message).toMatch(/not an LLM/i)
  })

  it('recognises origin codes and city names from the dataset', () => {
    const result = parsePrompt('Warm trip from ZAG to Rome', {
      origins: ['ZAG'],
      cities: ['Rome', 'Malta'],
    })
    expect(result.ok).toBe(true)
    expect(result.filters.origin).toBe('ZAG')
    expect(result.city).toBe('Rome')
  })
})
