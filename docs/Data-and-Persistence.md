# Data and persistence

[Documentation index](README.md)

## Cosmos access assumptions

The repository opens existing containers and does not provision them. Partition values below describe how code reads/writes; they are not verification of deployed container definitions.

| Container | Access and contents |
|---|---|
| `origins` | Point reads use origin ID as item ID and partition value; searches resolve city/IATA metadata |
| `flights` | Queries use `origin_id` as partition value; saved-flight ID lookups query across partitions |
| `users` (configurable) | Email lookups use the hashed `email_normalized` partition value; configure `/email_normalized` and a unique key on that field |
| `user-flights` (configurable) | One document per user, item ID and partition value both user ID; configure `/id` |
| `user-activities` (configurable) | One document per user, item ID and partition value both user ID; configure `/id` |
| `hotels` (configurable) | Parameterized cross-partition ID and identity queries; code does not establish a partition-key path |

Flights return an allowlist of identifiers, route/date/price data, airline display fields, coordinates/photos, weather, and retrieval timestamps. Cosmos internal metadata is not the public flight contract. Queries are limited before Python sorting; no refresh cadence is implemented here.

## Identifier boundaries

An origin ID such as `zagreb-hr` is distinct from an IATA code such as `ZAG`. A recommendation's `destination_id` is the exact flight-offer document ID, not a city ID.

`hotel_destination_id` identifies a stored hotel destination document. Resolution uses city plus country or matching IATA metadata, constrained by country when available. IDs are not constructed from display names. Missing, ambiguous, or conflicting matches yield null. Destination IDs are expected to identify a unique hotel document across partitions.

Hotels are validated and sorted by Haversine distance from the stored reference point using an Earth radius of 6,371 km. Invalid hotel entries are excluded. Invalid reference coordinates fail the lookup rather than substituting coordinates. `hotel_count` counts stored array entries before validation; `returned_count` counts returned entries. Missing hotel arrays can produce an empty successful response.

## Saved flights

Saving a flight fetches the current stored offer and persists an allowlisted snapshot for the session user. Saves are idempotent. Documents retain `flight_ids` for compatibility and snapshot data for details.

Listing checks the current flights container. Existing offers refresh changed snapshot fields and return as available. Missing offers return the saved snapshot as unavailable. Legacy ID-only entries without a current offer can have `flight: null`. Removing a saved flight does not delete the source offer.

## Saved activities

Activity documents contain snapshots keyed by Places `place_id`, with city/country/destination context. The saved-activity API accepts typed client activity data; it does not verify it by fetching Places again. Reads return snapshots, including any saved description, without provider refresh.

Nearby photos and map-link metadata are not all fields of the saved `ActivityItem` contract. Saving a nearby result does not imply that every nearby-response field is retained.

## Browser and process state

Saved flights and activities live in Cosmos. Passwords and session tokens are not stored in localStorage. The frontend separately stores hotel lookup IDs in localStorage by user ID and flight ID after a successful save, and removes them after successful deletion. This stores IDs, not hotel lists, and only survives in that browser/origin. Missing or disabled storage leaves hotel details unavailable for saves whose response lacks an ID.

Planner conversation/history is frontend state, not a durable backend conversation store. The explanation cache is process-local. Neither is a cross-device persistence mechanism.

Sources: [Cosmos repository](../backend/repositories/cosmos.py), [saved flights](../backend/services/saved_flights.py), [saved activities](../backend/services/saved_activities.py), [hotel service](../backend/services/hotels.py), [browser hotel metadata](../frontend/src/utils/savedHotelMetadata.js).
