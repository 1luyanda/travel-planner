# Ranking and recommendations

[Documentation index](README.md)

## Retrieval and validation

Recommend parses text/form fields and resolves the explicit origin IATA code through stored origins. Missing or ambiguous matches return `needs_input`. Candidate preparation validates stored values and applies hard constraints before scoring. Invalid data and constraint failures have structured rejection reasons; records already excluded by the Cosmos query do not become rejection entries.

The recommend/refine pipeline filters by origin, dates, EUR budget, and direct-flight requirement. Non-EUR budgets are not converted or applied numerically to EUR fares; the response includes an issue. Additional minimum-temperature, country, maximum-changeover, and duration filters exist on the candidate endpoint, but are not all fields in the recommend request.

Round-trip changeovers and air duration are scoring inputs. Air duration is separate from trip duration. Precipitation probability is required; sunshine is optional. Candidate preparation accepts flat and nested records; JSON/CSV adapters exist for local ranking use, while HTTP uses Cosmos.

## Flexible dates

When both dates are supplied and fewer than five valid exact-date candidates remain, preparation searches again without date filters, retaining other constraints. Each actual departure and return date must be within seven days of its requested date. Invalid or reversed dates are excluded.

Alternative offers are deduplicated by flight ID and selected by total date displacement, then difference in trip length, then ID. Only enough alternatives to reach five candidates are added. An undated or partially dated candidate query does not trigger fallback.

The combined candidate pool is ranked by score and the recommendation response keeps at most five. Exact dates are not given a separate score priority. Actual/requested dates, per-item flags, `exact_match_count`, `fallback_count`, and `flexible_date_fallback_used` describe retrieval. Counts describe prepared candidates, not necessarily the final shortlist.

## Scoring

| Criterion | Weight field | Default | Default preference |
|---|---|---|---|
| Price in EUR | `price_weight` | 0.25 | Lower |
| Average maximum temperature | `weather_weight` | 0.20 | Higher |
| Precipitation probability | `precipitation_weight` | 0.10 | Lower |
| Sunshine hours | `sunshine_weight` | 0.10 | Higher |
| Round-trip changeovers | `changeovers_weight` | 0.20 | Lower |
| Round-trip air duration | `duration_weight` | 0.15 | Lower |

Weights are nonnegative and normalize to one; their total must be positive. Each criterion uses min-max normalization across candidates. For higher-is-better, the score is `(value - minimum) / (maximum - minimum)`; lower-is-better reverses it. Equal known values score 1. Missing sunshine scores 0 without redistributing its weight.

The final score sums weighted component scores. Descending-score ties preserve input order. Scores are relative to this candidate pool and are not probabilities. Temperature, sunshine, and precipitation directions can be overridden independently of their weights.

Omitted weights retain defaults. Older four-weight requests therefore also acquire the two 0.10 defaults before normalization. Explicitly setting both new weights to zero removes their contribution when no policy adjustment changes them.

## Feedback policy

Implemented preference codes include `stronger_price_preference`, `prefer_warmer`, `prefer_cooler`, `prefer_more_sunshine`, `prefer_less_sunshine`, `prefer_less_rain`, `prefer_more_rain`, `prefer_fewer_stops`, and `stronger_duration_preference`. The policy additionally accepts `prefer_colder` as an alias.

Each recognized event increases each targeted criterion's normalized weight by up to 0.10. Targets are deduplicated and adjusted together; other weights decrease proportionally within policy bounds of 0.05-0.70. Insufficient donor capacity scales increases down together. Opposing directions in one event retain the current direction but increase that criterion's importance once. Unknown intents preserve current preferences.

Cheaper does not lower the numeric budget. Fewer stops is a preference; direct flights only is a hard constraint. Initial warm/cool searches apply a temperature intent. The initial parser's weather vocabulary also maps some sunshine/rain form terms to warm/cool; explicit refinement has separate sunshine and rain intents.

Clients must carry returned `ranking_preferences` forward. A filter-only recommend with `preserve_ranking_preferences: true` reuses supplied effective weights without reapplying initial weather intent. Without supplied weights, initial intent still applies.

## Explanations

The LLM selects grounded evidence; numeric facts and scores come from ranked records. Explanations cannot change rank or scores. Empty ranked lists do not call the model. If explanation generation fails, orchestration still returns ranked items with blank summaries, empty evidence, and issues.

Refinement can reuse process-local cached summaries/evidence. Cache keys include destination ID, origin, dates, budget, currency, and moods; they do not include every scoring or source-data field. Reused text is not guaranteed to describe a newly changed preference, although returned scores and ranks are rebuilt.

Sources: [preparation](../backend/services/candidates.py), [orchestration](../backend/services/recommendations.py), [ranking interface](../ranking/interface.py), [scoring](../ranking/ranking.py), [policy](../ranking/policy.py), [feedback](../backend/services/feedback.py), [explanations](../backend/services/explanations.py).
