import { useEffect, useId, useRef, useState } from 'react'
import { searchOrigins } from '../services/travelApi'
import {
  formatOriginLabel,
  parseOriginItems,
  shouldClearOriginSelection,
} from '../utils/origins'
import styles from '../workspace.module.css'

const DEBOUNCE_MS = 300

export default function OriginSelect({
  value,
  onChange,
  error,
  inputRef,
  disabled = false,
}) {
  const listId = useId()
  const labelId = useId()
  const errorId = useId()
  const rootRef = useRef(null)
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [matches, setMatches] = useState([])
  const [status, setStatus] = useState('idle')
  const [searchError, setSearchError] = useState('')
  const [activeIndex, setActiveIndex] = useState(0)

  const selectedLabel = formatOriginLabel(value)

  useEffect(() => {
    if (!open) setQuery(selectedLabel)
  }, [open, selectedLabel])

  useEffect(() => {
    function onPointerDown(event) {
      if (!rootRef.current?.contains(event.target)) setOpen(false)
    }
    document.addEventListener('mousedown', onPointerDown)
    return () => document.removeEventListener('mousedown', onPointerDown)
  }, [])

  useEffect(() => {
    if (!open) return undefined
    const needle = query.trim()
    if (needle.length < 1) {
      setMatches([])
      setStatus('idle')
      setSearchError('')
      return undefined
    }

    const controller = new AbortController()
    setStatus('loading')
    const timer = window.setTimeout(async () => {
      try {
        const items = await searchOrigins(needle, { signal: controller.signal })
        const parsed = items.flatMap((item) => parseOriginItems(item, needle))
        setMatches(parsed)
        setSearchError('')
        setStatus(parsed.length ? 'ready' : 'empty')
        setActiveIndex(0)
      } catch (err) {
        if (err?.name === 'AbortError') return
        setMatches([])
        setSearchError(err.message || 'Could not search origins.')
        setStatus('error')
      }
    }, DEBOUNCE_MS)

    return () => {
      window.clearTimeout(timer)
      controller.abort()
    }
  }, [open, query])

  function choose(origin) {
    onChange(origin)
    setQuery(formatOriginLabel(origin))
    setOpen(false)
  }

  function onKeyDown(event) {
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setOpen(true)
      setActiveIndex((current) => Math.min(current + 1, Math.max(matches.length - 1, 0)))
      return
    }
    if (event.key === 'ArrowUp') {
      event.preventDefault()
      setOpen(true)
      setActiveIndex((current) => Math.max(current - 1, 0))
      return
    }
    if (event.key === 'Enter' && open) {
      event.preventDefault()
      event.stopPropagation()
      if (matches[activeIndex]) choose(matches[activeIndex])
      return
    }
    if (event.key === 'Escape') {
      setOpen(false)
      setQuery(selectedLabel)
    }
  }

  const listMessage =
    status === 'loading'
      ? 'Searching origins…'
      : status === 'error'
        ? searchError
        : status === 'empty'
          ? 'No matching origins'
          : status === 'idle'
            ? 'Type a city to search origins'
            : null

  const describedBy = error ? errorId : undefined

  return (
    <div className={styles.originField} ref={rootRef}>
      <label id={labelId} htmlFor="flying-from">
        Flying from
      </label>
      <div className={styles.originControl}>
        <input
          ref={inputRef}
          id="flying-from"
          type="text"
          role="combobox"
          autoComplete="off"
          spellCheck={false}
          disabled={disabled}
          placeholder="Search city, country, or IATA"
          value={open ? query : selectedLabel}
          aria-labelledby={labelId}
          aria-expanded={open}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-required="true"
          aria-invalid={Boolean(error)}
          aria-busy={status === 'loading'}
          aria-activedescendant={
            open && matches[activeIndex]
              ? `${listId}-${matches[activeIndex].selectionId || matches[activeIndex].originId}`
              : undefined
          }
          aria-describedby={describedBy}
          onChange={(event) => {
            const next = event.target.value
            setQuery(next)
            setOpen(true)
            if (shouldClearOriginSelection(value, next)) onChange(null)
          }}
          onFocus={(event) => {
            setOpen(true)
            event.target.select()
          }}
          onKeyDown={onKeyDown}
        />
        {open && (
          <ul id={listId} className={styles.originList} role="listbox" aria-label="Departure cities">
            {listMessage ? (
              <li className={styles.originEmpty} role="presentation">
                {listMessage}
              </li>
            ) : (
              matches.map((origin, index) => (
                <li key={origin.selectionId || origin.originId} role="presentation">
                  <button
                    type="button"
                    id={`${listId}-${origin.selectionId || origin.originId}`}
                    role="option"
                    className={index === activeIndex ? styles.originOptionActive : styles.originOption}
                    aria-selected={origin.originId === value?.originId}
                    onMouseDown={(event) => event.preventDefault()}
                    onMouseEnter={() => setActiveIndex(index)}
                    onClick={() => choose(origin)}
                  >
                    <strong>{origin.city || origin.originId}</strong>
                    <span>
                      {[origin.country, origin.iata].filter(Boolean).join(' · ')}
                    </span>
                  </button>
                </li>
              ))
            )}
          </ul>
        )}
      </div>
      {error && (
        <p id={errorId} className={styles.originError} role="alert">
          {error}
        </p>
      )}
    </div>
  )
}
