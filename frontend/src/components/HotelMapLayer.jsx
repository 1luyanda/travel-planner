import { BedDouble } from 'lucide-react'
import { formatHotelDistance } from '../utils/hotels'
import PlaceMapLayer from './PlaceMapLayer'

function renderHotelPopup(marker) {
  return <>
    <strong>{marker.hotel.name}</strong>
    <p>Approx. {formatHotelDistance(marker.hotel.distance_km)} from destination centre</p>
  </>
}

export default function HotelMapLayer({ markers, selectedHotelId, focusVersion, onSelectHotel, onFocus }) {
  return <PlaceMapLayer markers={markers} selectedKey={selectedHotelId} focusVersion={focusVersion}
    onSelect={onSelectHotel} onFocus={onFocus} Icon={BedDouble}
    markerClassName="hotel-map-marker" renderPopup={renderHotelPopup} />
}
