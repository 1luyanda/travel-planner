/** Hotel identity and coordinates are independent of destination pin grouping. */
export function hotelKey(hotel) {
  return hotel.osm_id || JSON.stringify([hotel.name, hotel.latitude ?? null, hotel.longitude ?? null])
}

export function hotelPosition(hotel) {
  const { latitude, longitude } = hotel
  return Number.isFinite(latitude) && Number.isFinite(longitude)
    && Math.abs(latitude) <= 90 && Math.abs(longitude) <= 180
    ? [latitude, longitude] : null
}

export function buildHotelMarkers(hotels = []) {
  return hotels.flatMap((hotel) => {
    const position = hotelPosition(hotel)
    return position ? [{ key: hotelKey(hotel), position, hotel }] : []
  })
}
