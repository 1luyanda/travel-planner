/** Activity pins use the Google place location returned with each activity. */
export function activityPosition(activity) {
  const { latitude, longitude } = activity
  return Number.isFinite(latitude) && Number.isFinite(longitude)
    && Math.abs(latitude) <= 90 && Math.abs(longitude) <= 180
    ? [latitude, longitude] : null
}

export function buildActivityMarkers(activities = []) {
  return activities.flatMap((activity) => {
    const position = activityPosition(activity)
    return position
      ? [{ key: activity.place_id, position, label: activity.name, activity }]
      : []
  })
}
