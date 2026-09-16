import { describe, expect, it } from 'vitest'
import {
  ORIGIN_REQUIRED_MESSAGE,
  formatOriginLabel,
  isValidOriginSelection,
  parseOriginItem,
  requireSelectedOrigin,
  shouldClearOriginSelection,
} from './origins'

const zagrebDoc = {
  id: 'zagreb-hr',
  city: 'Zagreb',
  country: 'Croatia',
  country_code: 'HR',
  airports: ['ZAG'],
  city_iata: ['ZAG'],
  flight_count: 154,
  photo_url: 'https://example.com/zagreb.jpg',
}

describe('parseOriginItem', () => {
  it('stores origin_id separately from IATA', () => {
    const origin = parseOriginItem(zagrebDoc)
    expect(origin.originId).toBe('zagreb-hr')
    expect(origin.iata).toBe('ZAG')
    expect(origin.originId).not.toBe(origin.iata)
    expect(origin.city).toBe('Zagreb')
    expect(origin.country).toBe('Croatia')
  })

  it('does not invent an origin without an id', () => {
    expect(parseOriginItem({ city: 'Zagreb', city_iata: ['ZAG'] })).toBeNull()
  })
})

describe('requireSelectedOrigin', () => {
  it('requires an explicit origin_id selection, not an IATA code', () => {
    expect(requireSelectedOrigin(null)).toEqual({
      ok: false,
      message: ORIGIN_REQUIRED_MESSAGE,
    })
    expect(requireSelectedOrigin({ originId: 'ZAG', iata: 'ZAG' }).ok).toBe(false)
    expect(requireSelectedOrigin(parseOriginItem(zagrebDoc))).toEqual({ ok: true })
  })
})

describe('formatOriginLabel', () => {
  it('shows city, country and IATA when available', () => {
    expect(formatOriginLabel(parseOriginItem(zagrebDoc))).toBe('Zagreb, Croatia (ZAG)')
  })
})

describe('shouldClearOriginSelection', () => {
  it('clears the selection after the user edits the selected label', () => {
    const origin = parseOriginItem(zagrebDoc)
    expect(shouldClearOriginSelection(origin, formatOriginLabel(origin))).toBe(false)
    expect(shouldClearOriginSelection(origin, 'Lisbon')).toBe(true)
  })
})

describe('isValidOriginSelection', () => {
  it('rejects using IATA as origin_id', () => {
    expect(isValidOriginSelection({ originId: 'ZAG', iata: 'ZAG' })).toBe(false)
    expect(isValidOriginSelection({ originId: 'zagreb-hr', iata: 'ZAG' })).toBe(true)
  })
})
