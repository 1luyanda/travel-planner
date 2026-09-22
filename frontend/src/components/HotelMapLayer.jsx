import { useEffect, useMemo, useRef } from 'react'
import { createPortal } from 'react-dom'
import { BedDouble } from 'lucide-react'
import { Marker, Popup, useMap } from 'react-leaflet'
import L from 'leaflet'
import { formatHotelDistance } from '../utils/hotels'

function HotelMarker({ marker, selected, markerRefs, onSelectHotel }) {
  const iconHost = useMemo(() => document.createElement('span'), [])
  const icon = useMemo(() => L.divIcon({
    className: `hotel-map-marker${selected ? ' is-selected' : ''}`,
    html: iconHost,
    iconSize: [24, 24], iconAnchor: [12, 12], popupAnchor: [0, -12],
  }), [iconHost, selected])

  return <>
    {createPortal(<BedDouble size={14} aria-hidden="true" />, iconHost)}
    <Marker position={marker.position} icon={icon}
      title={marker.hotel.name} alt={marker.hotel.name}
      zIndexOffset={selected ? 500 : -100}
      ref={(instance) => {
        if (instance) markerRefs.current.set(marker.key, instance)
        else markerRefs.current.delete(marker.key)
      }}
      eventHandlers={{ click: () => onSelectHotel?.(marker.key) }}>
      <Popup autoPan={false}>
        <strong>{marker.hotel.name}</strong>
        <p>Approx. {formatHotelDistance(marker.hotel.distance_km)} from destination centre</p>
      </Popup>
    </Marker>
  </>
}

export default function HotelMapLayer({ markers, selectedHotelId, focusVersion, onSelectHotel, onFocus }) {
  const map = useMap()
  const refs = useRef(new Map())
  const selected = markers.find((marker) => marker.key === selectedHotelId)
  const latitude = selected?.position[0]
  const longitude = selected?.position[1]

  useEffect(() => {
    if (latitude == null || longitude == null) {
      refs.current.forEach((marker) => marker.closePopup())
      return undefined
    }
    const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    map.stop()
    map.panTo([latitude, longitude], { animate: !reduced })
    refs.current.get(selectedHotelId)?.openPopup()
    onFocus?.()
    return undefined
  }, [map, selectedHotelId, latitude, longitude, focusVersion, onFocus])

  return markers.map((marker) => (
    <HotelMarker key={marker.key} marker={marker} selected={marker.key === selectedHotelId}
      markerRefs={refs} onSelectHotel={onSelectHotel} />
  ))
}
