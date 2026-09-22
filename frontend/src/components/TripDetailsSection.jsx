import { useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'

export default function TripDetailsSection({ title, headingId, defaultExpanded = false, children }) {
  const [expanded, setExpanded] = useState(defaultExpanded)
  const contentId = `${headingId}-content`
  const Chevron = expanded ? ChevronDown : ChevronRight
  return (
    <section className="trip-details-activities" aria-labelledby={headingId}>
      <h3 id={headingId}>
        <button type="button" className="trip-details-section-toggle"
          aria-expanded={expanded} aria-controls={contentId}
          onClick={() => setExpanded((value) => !value)}>
          {title}<Chevron size={16} aria-hidden="true" />
        </button>
      </h3>
      <div id={contentId} hidden={!expanded}>{children}</div>
    </section>
  )
}
