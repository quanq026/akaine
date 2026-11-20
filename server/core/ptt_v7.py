"""Arcaea 7.x total-potential aggregation, drop-in for Arcaea-Server style codebases.

Rules (v7): no Recent 10; take the best 50 play ratings (one per chart);
the top 10 of those count double. Per-play rating is NOT touched here.

    potential = (TOP_WEIGHT * sum(top 10) + sum(rank 11..50)) / DIVISOR

DIVISOR defaults to TOP_COUNT * TOP_WEIGHT + (BEST_COUNT - TOP_COUNT) = 60 and is
always applied, even if the player has fewer than 50 scores (same behaviour as the
v6 "/ 40"). Override it if the official value turns out to differ.
"""
from typing import Iterable, Optional

BEST_COUNT = 50
TOP_COUNT = 10
TOP_WEIGHT = 2


def default_divisor(best_count: int = BEST_COUNT, top_count: int = TOP_COUNT,
                    top_weight: int = TOP_WEIGHT) -> int:
    return top_count * top_weight + (best_count - top_count)


def potential_v7(ratings: Iterable[float],
                 best_count: int = BEST_COUNT,
                 top_count: int = TOP_COUNT,
                 top_weight: int = TOP_WEIGHT,
                 divisor: Optional[float] = None) -> float:
    """`ratings` = best play rating of each chart (unranked = -1 is treated as 0)."""
    if divisor is None:
        divisor = default_divisor(best_count, top_count, top_weight)
    best = sorted((max(float(r), 0.0) for r in ratings), reverse=True)[:best_count]
    return (top_weight * sum(best[:top_count]) + sum(best[top_count:])) / divisor

def stored_potential(value: float) -> int:
    """Convert to the shared database's integer hundredths."""
    return int(value * 100 + 1e-9)


def best_potential(cursor, user_id: int) -> float:
    cursor.execute(
        "SELECT rating FROM best_score WHERE user_id = ? AND rating > 0 "
        "ORDER BY rating DESC LIMIT ?", (user_id, BEST_COUNT))
    return potential_v7(row[0] for row in cursor.fetchall())
