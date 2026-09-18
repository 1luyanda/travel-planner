import { describe, expect, it } from 'vitest'
import {
  clearTripSelection,
  resolveSelectedTrip,
  selectTripFromResult,
  selectionAfterPoolChange,
  tripFromMarkerId,
} from './tripDetailsSelection'

const rome = { id: 'ZAG-ROM-2026-09-18', destination: { city: 'Rome' } }
const lisbon = { id: 'ZAG-LIS-2026-09-18', destination: { city: 'Lisbon' } }
const romeRefined = { ...rome, flight: { price: 54 } }

describe('trip details selection', () => {
  it('selects a trip and switches to another by id', () => {
    const selected = selectTripFromResult(rome)
    expect(selected).toEqual({
      selectedTrip: rome,
      selectedDestinationId: rome.id,
      viewportMode: 'selected',
    })
    expect(resolveSelectedTrip([rome, lisbon], selected.selectedTrip)?.destination.city).toBe('Rome')
    expect(resolveSelectedTrip([rome, lisbon], lisbon)?.id).toBe(lisbon.id)
  })

  it('clears selection without touching the result list', () => {
    const results = [rome, lisbon]
    expect(clearTripSelection()).toEqual({
      selectedTrip: null,
      selectedDestinationId: null,
      viewportMode: 'bounds',
    })
    expect(results).toEqual([rome, lisbon])
  })

  it('updates the selected trip from refined results with the same id', () => {
    const next = selectionAfterPoolChange([romeRefined, lisbon], rome, rome.id)
    expect(next.selectedTrip).toEqual(romeRefined)
    expect(next.selectedTrip.flight.price).toBe(54)
    expect(next.selectedDestinationId).toBe(rome.id)
  })

  it('clears selection when the selected trip disappears after refinement', () => {
    const next = selectionAfterPoolChange([lisbon], rome, rome.id)
    expect(next.selectedTrip).toBeNull()
    expect(next.selectedDestinationId).toBeNull()
  })

  it('maps a marker id onto a result only when that id exists', () => {
    expect(tripFromMarkerId([rome, lisbon], rome.id)).toEqual(rome)
    expect(tripFromMarkerId([rome, lisbon], 'missing')).toBeNull()
  })
})
