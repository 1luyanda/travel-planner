# User guide

[Documentation index](README.md)

## Plan a trip

Guests can use `/planner`. Enter travel requirements in the composer and optionally select an origin from autocomplete or use the form filters. A ready request requires an explicit origin IATA code, departure and return dates, a positive budget, and currency. Respond to clarification questions if details are missing or the origin is ambiguous.

Results show a ranked shortlist with stored flight details and explanations when available. Scores compare the current candidate set; they are not confidence percentages. Results can include alternative dates within seven days of each requested date when too few exact matches exist. Read the displayed actual dates and flexible-date notice before saving.

Refine with preferences such as cheaper, warmer, cooler, more sunshine, less rain, fewer stops, or shorter flights. A preference changes scoring; a numeric budget or direct-flights-only requirement changes filtering. Filter updates preserve the effective preference weights.

## Inspect trip details

Select a result to open details. Hotels are ordered by approximate straight-line distance from the stored destination reference point. Hotel cards and map markers share selection. Optional stars and official website links are displayed when supplied. Hotel prices and availability are not provided.

Hotels start expanded and Activities collapsed. Section toggles preserve mounted content. Hotels load when details open or the hotel destination changes; closing and reopening refreshes them. Failed loads have a Retry action. Missing hotel IDs and empty results have an empty state.

Activities come from Google Places. Descriptions are supplied editorial summaries, not generated descriptions; some places have none. Activities can be liked by authenticated users.

## Accounts and saved items

Use `/signup` to create an account with email, display name, and a password of 12 to 128 characters. `/login` authenticates an existing account. Signing in sets an HttpOnly session cookie. The current login response derives the display name from the email prefix rather than restoring the originally entered name.

Save a flight to retain it in your account independently of the active shortlist and filters. Saved flights refresh from stored flight data when listed. If an offer disappears from the flights container, its snapshot remains visible as unavailable. Removing an item affects your saved list.

Liked activities are snapshots and are not refreshed from Places when read later. Hotel lookup IDs associated with saved flights are retained separately in the same browser, scoped to user and flight. They do not sync to another browser or device.

## Explore nearby activities

`/explore` requires login in the frontend. Search by city and activity category, or explicitly use the browser location control. Browser permission is required for geolocation. Results can include photos, ratings, summaries, map links, and map markers when supplied by Places.

The backend nearby endpoint accepts coordinates or a city and is protected by the proxy API key; the frontend login redirect is separate from backend session authorization. See [API reference](API-Reference.md).

Sources: [routing](../frontend/src/utils/routes.jsx), [planner application](../frontend/src/App.jsx), [Explore](../frontend/src/components/ExplorePane.jsx), [trip details](../frontend/src/components/TripDetailsContent.jsx), [authentication routes](../backend/api/auth.py).
