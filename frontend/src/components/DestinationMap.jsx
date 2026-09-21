import { useEffect, useMemo, useRef } from 'react'
import { MapContainer, Marker, Popup, TileLayer, useMap } from 'react-leaflet'
import L from 'leaflet'
import markerIcon from 'leaflet/dist/images/marker-icon.png'
import markerIcon2x from 'leaflet/dist/images/marker-icon-2x.png'
import markerShadow from 'leaflet/dist/images/marker-shadow.png'
import 'leaflet/dist/leaflet.css'
import { buildMapMarkers, findMarkerForSelection } from '../utils/mapMarkers'
import styles from '../workspace.module.css'

delete L.Icon.Default.prototype._getIconUrl
L.Icon.Default.mergeOptions({
  iconRetinaUrl: markerIcon2x,
  iconUrl: markerIcon,
  shadowUrl: markerShadow,
})

const CITY_ZOOM = 10

function prefersReducedMotion() {
  return typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches
}

function MapResize() {
  const map = useMap()

  useEffect(() => {
    const container = map.getContainer()
    const invalidate = () => map.invalidateSize({ debounceMoveend: true, pan: false })
    const observer = new ResizeObserver(() => {
      if (container.offsetWidth > 0 && container.offsetHeight > 0) invalidate()
    })
    observer.observe(container)
    if (container.parentElement) observer.observe(container.parentElement)
    invalidate()
    return () => observer.disconnect()
  }, [map])

  return null
}

function MapViewport({ markers, selectedId, viewportMode, markerRefs }) {
  const map = useMap()
  const markerSignature = markers.map((item) => `${item.key}:${item.position.join(',')}`).join('|')

  useEffect(() => {
    if (!markers.length) return undefined
    const reduced = prefersReducedMotion()
    const selected = findMarkerForSelection(markers, selectedId)

    if (viewportMode === 'selected' && selected) {
      if (reduced) map.setView(selected.position, CITY_ZOOM, { animate: false })
      else map.flyTo(selected.position, CITY_ZOOM)
      const openPopup = () => markerRefs.current.get(selected.key)?.openPopup()
      map.once('moveend', openPopup)
      const timer = window.setTimeout(openPopup, reduced ? 0 : 400)
      return () => {
        map.off('moveend', openPopup)
        window.clearTimeout(timer)
      }
    }

    if (markers.length === 1) {
      map.setView(markers[0].position, CITY_ZOOM, { animate: !reduced })
      return undefined
    }

    map.fitBounds(
      markers.map((item) => item.position),
      { padding: [36, 36], maxZoom: 12, animate: !reduced },
    )
    return undefined
  }, [map, markerSignature, markers, selectedId, viewportMode, markerRefs])

  return null
}

export default function DestinationMap({
  results,
  selectedId,
  viewportMode,
  onSelectMarker,
  onShowAll,
}) {
  const markers = useMemo(() => buildMapMarkers(results), [results])
  const markerRefs = useRef(new Map())

  if (!markers.length) {
    return (
      <section className={styles.mapEmpty} aria-labelledby="map-title">
        <h2 id="map-title">Destination map</h2>
        <p>
          {results?.length
            ? 'These trips are listed, but none have valid destination coordinates to map.'
            : 'No mapped destinations for these results. Pins need valid destination coordinates.'}
        </p>
      </section>
    )
  }

  return (
    <section className={styles.mapPane} aria-labelledby="map-title">
      <h2 id="map-title" className={styles.srOnly}>
        Destination map
      </h2>
      <MapContainer
        center={markers[0].position}
        zoom={CITY_ZOOM}
        scrollWheelZoom
        className={styles.mapCanvas}
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <MapResize />
        <MapViewport
          markers={markers}
          selectedId={selectedId}
          viewportMode={viewportMode}
          markerRefs={markerRefs}
        />
        {markers.map((marker) => {
          const isSelected = marker.resultIds.includes(selectedId)
          return (
            <Marker
              key={marker.key}
              position={marker.position}
              zIndexOffset={isSelected ? 1000 : 0}
              ref={(instance) => {
                if (instance) markerRefs.current.set(marker.key, instance)
                else markerRefs.current.delete(marker.key)
              }}
              eventHandlers={{
                click: () => onSelectMarker?.(marker.id),
              }}
            >
              <Popup>
                <div className={styles.mapPopup}>
                  <strong>
                    {[marker.destination_city, marker.destination_country].filter(Boolean).join(', ')}
                  </strong>
                  {marker.airport_name ? <p>{marker.airport_name}</p> : null}
                  {marker.priceLine ? <p>{marker.priceLine}</p> : null}
                </div>
              </Popup>
            </Marker>
          )
        })}
      </MapContainer>
      <button type="button" className={styles.showAll} onClick={onShowAll}>
        Show all destinations
      </button>
    </section>
  )
}
