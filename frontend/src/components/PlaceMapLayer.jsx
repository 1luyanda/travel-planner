import { useEffect, useMemo, useRef } from 'react'
import { createPortal } from 'react-dom'
import { Marker, Popup, useMap } from 'react-leaflet'
import L from 'leaflet'

/** Street-level zoom so a selected hotel or activity stands apart from its neighbours. */
export const PLACE_ZOOM = 16

function PlaceMarker({ marker, selected, markerRefs, onSelect, Icon, markerClassName, renderPopup }) {
  const iconHost = useMemo(() => document.createElement('span'), [])
  const icon = useMemo(() => L.divIcon({
    className: `${markerClassName}${selected ? ' is-selected' : ''}`,
    html: iconHost,
    iconSize: [24, 24], iconAnchor: [12, 12], popupAnchor: [0, -12],
  }), [iconHost, selected, markerClassName])

  return <>
    {createPortal(<Icon size={14} aria-hidden="true" />, iconHost)}
    <Marker position={marker.position} icon={icon}
      title={marker.label} alt={marker.label}
      zIndexOffset={selected ? 500 : -100}
      ref={(instance) => {
        if (instance) markerRefs.current.set(marker.key, instance)
        else markerRefs.current.delete(marker.key)
      }}
      eventHandlers={{ click: () => onSelect?.(marker.key) }}>
      <Popup autoPan={false}>{renderPopup(marker)}</Popup>
    </Marker>
  </>
}

/** Secondary pins (hotels, activities) that zoom the map in on the selected one. */
export default function PlaceMapLayer({
  markers, selectedKey, focusVersion, onSelect, onFocus, Icon, markerClassName, renderPopup,
}) {
  const map = useMap()
  const refs = useRef(new Map())
  const selected = markers.find((marker) => marker.key === selectedKey)
  const latitude = selected?.position[0]
  const longitude = selected?.position[1]

  useEffect(() => {
    if (latitude == null || longitude == null) {
      refs.current.forEach((marker) => marker.closePopup())
      return undefined
    }
    const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    const zoom = Math.max(map.getZoom(), PLACE_ZOOM)
    map.stop()
    if (reduced) map.setView([latitude, longitude], zoom, { animate: false })
    else map.flyTo([latitude, longitude], zoom)
    refs.current.get(selectedKey)?.openPopup()
    onFocus?.()
    return undefined
  }, [map, selectedKey, latitude, longitude, focusVersion, onFocus])

  return markers.map((marker) => (
    <PlaceMarker key={marker.key} marker={marker} selected={marker.key === selectedKey}
      markerRefs={refs} onSelect={onSelect} Icon={Icon}
      markerClassName={markerClassName} renderPopup={renderPopup} />
  ))
}
