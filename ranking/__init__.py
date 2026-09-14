"""Stable public imports for the ``ranking`` package.

This file lets callers write:

    from ranking import prepare_ranking_records, RankingConstraints

instead of depending on the internal file location:

    from ranking.interface import prepare_ranking_records, RankingConstraints

Keeping public imports here means ``interface.py`` can later be renamed or
split into multiple files without forcing the ranking developer to update
their imports.
"""

# Re-export the parts of interface.py that other project modules may use.
from .interface import (
    CandidatePreparationResult,
    RankedDestination,
    RankingCandidate,
    RankingConstraints,
    RankingDataError,
    RejectedCandidate,
    Rejection,
    prepare_ranking_data,
    prepare_ranking_records,
)
from .ranking import rank_destinations

# ``__all__`` documents the supported public API and controls what is exported
# by ``from ranking import *``. Names not listed here should be treated as
# implementation details.
__all__ = [
    "CandidatePreparationResult",
    "RankedDestination",
    "RankingCandidate",
    "RankingConstraints",
    "RankingDataError",
    "RejectedCandidate",
    "Rejection",
    "prepare_ranking_data",
    "prepare_ranking_records",
    "rank_destinations",
]
