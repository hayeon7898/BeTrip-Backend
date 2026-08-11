from dataclasses import dataclass
from itertools import permutations
from typing import Literal

TimeSlot = Literal["MORNING", "LUNCH", "EVENING"]

_TIME_SLOTS: list[TimeSlot] = ["MORNING", "LUNCH", "EVENING"]
_SLOT_BASE_TIME_MINUTES: dict[TimeSlot, int] = {
    "MORNING": 9 * 60,
    "LUNCH": 12 * 60,
    "EVENING": 18 * 60,
}
VISIT_DURATION_MIN = 90
_MAX_BRUTE_FORCE_SIZE = 8
_KMEANS_ITERATIONS = 10


@dataclass(frozen=True)
class PlaceCoord:
    """클러스터링/순서 계산에 필요한 최소 정보만 담는 값 객체."""

    key: str  # itinerary_place_id 등 호출자가 결과를 다시 식별할 때 쓰는 키
    lat: float
    lng: float


def _distance(a: PlaceCoord, b: PlaceCoord) -> float:
    """지역 내 소규모 거리 비교용 유클리드 근사 (haversine 불필요)."""
    return ((a.lat - b.lat) ** 2 + (a.lng - b.lng) ** 2) ** 0.5


def cluster_by_day(
    places: list[PlaceCoord], num_days: int
) -> dict[int, list[PlaceCoord]]:
    """장소들을 num_days개의 day(1-indexed)에 지리적으로 배분한다.

    장소 수가 day 수 이하면 클러스터링이 무의미하므로 라운드로빈으로 하루 1개씩 배정.
    그 외에는 위경도 기준 단순 k-means(k=num_days)로 배분한다.
    """
    result: dict[int, list[PlaceCoord]] = {day: [] for day in range(1, num_days + 1)}

    if not places:
        return result

    if len(places) <= num_days:
        for idx, place in enumerate(places):
            result[idx + 1].append(place)
        return result

    centroids = _init_centroids(places, num_days)
    assignments = [0] * len(places)

    for _ in range(_KMEANS_ITERATIONS):
        changed = False
        for i, place in enumerate(places):
            nearest = min(
                range(num_days),
                key=lambda c: _distance(place, centroids[c]),
            )
            if assignments[i] != nearest:
                assignments[i] = nearest
                changed = True

        clusters: list[list[PlaceCoord]] = [[] for _ in range(num_days)]
        for i, place in enumerate(places):
            clusters[assignments[i]].append(place)

        _fix_empty_clusters(clusters, assignments, places)
        centroids = [_centroid(cluster) for cluster in clusters]

        if not changed:
            break

    for i, place in enumerate(places):
        result[assignments[i] + 1].append(place)
    return result


def _init_centroids(places: list[PlaceCoord], k: int) -> list[PlaceCoord]:
    """정렬 후 등간격으로 초기 중심점을 뽑아 결정적으로(deterministic) 초기화."""
    ordered = sorted(places, key=lambda p: (p.lat, p.lng))
    step = max(len(ordered) // k, 1)
    centroids = [ordered[min(i * step, len(ordered) - 1)] for i in range(k)]
    return centroids


def _centroid(cluster: list[PlaceCoord]) -> PlaceCoord:
    if not cluster:
        return PlaceCoord(key="", lat=0.0, lng=0.0)
    lat = sum(p.lat for p in cluster) / len(cluster)
    lng = sum(p.lng for p in cluster) / len(cluster)
    return PlaceCoord(key="", lat=lat, lng=lng)


def _fix_empty_clusters(
    clusters: list[list[PlaceCoord]],
    assignments: list[int],
    places: list[PlaceCoord],
) -> None:
    """빈 클러스터가 생기면 가장 큰 클러스터에서 중심점과 가장 먼 포인트를 뺏어온다."""
    for c_idx, cluster in enumerate(clusters):
        if cluster:
            continue
        donor_idx = max(range(len(clusters)), key=lambda i: len(clusters[i]))
        if len(clusters[donor_idx]) <= 1:
            continue
        donor_centroid = _centroid(clusters[donor_idx])
        farthest = max(clusters[donor_idx], key=lambda p: _distance(p, donor_centroid))
        clusters[donor_idx].remove(farthest)
        cluster.append(farthest)
        assignments[places.index(farthest)] = c_idx


def order_within_day(places: list[PlaceCoord]) -> list[PlaceCoord]:
    """하루치 장소를 이동거리가 최소가 되는 순서로 정렬한다(소규모 TSP).

    장소 수가 적으면(<= 8) 완전탐색으로 정확한 최적해를 구하고,
    많아지면 nearest-neighbor greedy로 근사한다.
    """
    if len(places) <= 1:
        return list(places)

    if len(places) <= _MAX_BRUTE_FORCE_SIZE:
        start, rest = places[0], places[1:]
        best_order = None
        best_distance = float("inf")
        for perm in permutations(rest):
            candidate = (start, *perm)
            total = sum(
                _distance(candidate[i], candidate[i + 1])
                for i in range(len(candidate) - 1)
            )
            if total < best_distance:
                best_distance = total
                best_order = candidate
        return list(best_order)

    remaining = list(places[1:])
    ordered = [places[0]]
    while remaining:
        nearest = min(remaining, key=lambda p: _distance(ordered[-1], p))
        ordered.append(nearest)
        remaining.remove(nearest)
    return ordered


def assign_time_slots(
    ordered_places: list[PlaceCoord],
    *,
    is_first_day: bool,
    is_last_day: bool,
    arrival_time: TimeSlot,
    departure_time: TimeSlot,
) -> list[tuple[PlaceCoord, TimeSlot]]:
    """순서가 정해진 하루치 장소를 MORNING/LUNCH/EVENING 슬롯에 균등 배분한다.

    첫날은 arrival_time 이전 슬롯을, 마지막날은 departure_time 이후 슬롯을 제외한다.
    """
    if not ordered_places:
        return []

    available = list(_TIME_SLOTS)
    if is_first_day:
        arrival_idx = _TIME_SLOTS.index(arrival_time)
        available = [s for s in available if _TIME_SLOTS.index(s) >= arrival_idx]
    if is_last_day:
        departure_idx = _TIME_SLOTS.index(departure_time)
        available = [s for s in available if _TIME_SLOTS.index(s) <= departure_idx]
    if not available:
        available = [arrival_time]

    n = len(ordered_places)
    num_slots = len(available)
    base, extra = divmod(n, num_slots)

    result: list[tuple[PlaceCoord, TimeSlot]] = []
    cursor = 0
    for slot_idx, slot in enumerate(available):
        count = base + (1 if slot_idx < extra else 0)
        for place in ordered_places[cursor : cursor + count]:
            result.append((place, slot))
        cursor += count
    return result


def _format_minutes(total_minutes: int) -> str:
    hours, minutes = divmod(total_minutes % (24 * 60), 60)
    return f"{hours:02d}:{minutes:02d}"


def compute_start_times(
    slotted_items: list[tuple[PlaceCoord, TimeSlot]],
    travel_minutes: list[int | None],
) -> list[str]:
    """슬롯 배정된 순서대로 시작시각을 계산한다.

    각 슬롯 진입 시 슬롯 기준시각보다 이르면 기준시각으로 맞추고,
    이후엔 이전 방문(체류시간+이동시간) 누적으로 흘러간다.
    travel_minutes[i]는 i번째 장소에서 다음 장소까지의 이동시간(마지막 원소는 미사용).
    """
    if not slotted_items:
        return []

    start_times: list[str] = []
    clock: int | None = None
    prev_slot: TimeSlot | None = None

    for idx, (_, slot) in enumerate(slotted_items):
        slot_base = _SLOT_BASE_TIME_MINUTES[slot]
        if clock is None or slot != prev_slot and clock < slot_base:
            clock = slot_base
        start_times.append(_format_minutes(clock))
        prev_slot = slot

        if idx < len(slotted_items) - 1:
            travel = travel_minutes[idx] or 0
            clock += VISIT_DURATION_MIN + travel

    return start_times
