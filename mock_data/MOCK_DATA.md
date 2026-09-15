# Mock Data Files

Running `destination_pipeline.py` creates the following files inside `mock_data/`.

## `travelpayouts_flights.json`

Contains cached flight offers returned by Travelpayouts, including:

- Origin and destination
- Price and currency
- Departure and return dates
- Stops and flight duration
- Airline and flight number

Used to develop and test flight searching without repeatedly calling Travelpayouts.

## `travelpayouts_cities.json`

Contains metadata for the destination cities used in the flight results:

- City name and IATA code
- Country code
- Coordinates
- Time zone

Used to connect flight destinations with weather and country data.

## `travelpayouts_airports.json`

Contains metadata for airports used in the flight results:

- Airport name and IATA code
- City and country codes
- Coordinates
- Time zone

Used to display airport details and obtain accurate weather coordinates.

## `open_meteo_weather.json`

Contains weather forecasts for each destination:

- Daily minimum and maximum temperature
- Precipitation probability
- Weather code
- Sunshine duration
- Maximum wind speed
- Time zone

Used to calculate weather suitability and display weather information.

## `rest_countries.json`

Contains country information for the destination countries:

- Common and official country names
- ISO country codes
- Capitals
- Currencies
- Languages
- Region and subregion
- Flags
- Time zones

Used to enrich destination cards with readable country details.

## `normalized_destinations.json`

Contains the combined application-ready records created from all three APIs.

Each record contains:

- Flight details
- Destination and airport information
- Weather summary
- Country information
- Retrieval timestamps

This is the main mock file that the ranking engine and frontend should use.
