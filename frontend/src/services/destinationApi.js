/**
 * /api/destinations was removed. Use travelApi.js for origins, recommend/refine,
 * and optional candidates/flights enrichment.
 */
export {
  ApiError,
  fetchCandidates,
  fetchFlights,
  fetchOrigin,
  recommendTrip,
  refineTrip,
  searchOrigins,
} from './travelApi'
