import { Landmark } from 'lucide-react'
import PlaceMapLayer from './PlaceMapLayer'

function renderActivityPopup(marker) {
  return <>
    <strong>{marker.activity.name}</strong>
    {marker.activity.address ? <p>{marker.activity.address}</p> : null}
  </>
}

export default function ActivityMapLayer({ markers, selectedActivityId, focusVersion, onSelectActivity, onFocus }) {
  return <PlaceMapLayer markers={markers} selectedKey={selectedActivityId} focusVersion={focusVersion}
    onSelect={onSelectActivity} onFocus={onFocus} Icon={Landmark}
    markerClassName="activity-map-marker" renderPopup={renderActivityPopup} />
}
