from app.utils.itinerary_planner import (
    PlaceCoord,
    assign_time_slots,
    cluster_by_day,
    compute_start_times,
    order_within_day,
)


class TestClusterByDay:
    def test_fewer_places_than_days_round_robins_one_per_day(self):
        places = [PlaceCoord("a", 33.4, 126.5), PlaceCoord("b", 33.5, 126.6)]

        result = cluster_by_day(places, num_days=3)

        assert [p.key for p in result[1]] == ["a"]
        assert [p.key for p in result[2]] == ["b"]
        assert result[3] == []

    def test_no_places_returns_empty_days(self):
        result = cluster_by_day([], num_days=2)

        assert result == {1: [], 2: []}

    def test_geographically_separated_groups_split_by_day(self):
        west = [
            PlaceCoord(f"w{i}", 33.4 + i * 0.001, 126.2 + i * 0.001) for i in range(4)
        ]
        east = [
            PlaceCoord(f"e{i}", 33.5 + i * 0.001, 126.9 + i * 0.001) for i in range(4)
        ]

        result = cluster_by_day(west + east, num_days=2)

        keys_by_day = {day: {p.key for p in places} for day, places in result.items()}
        assert keys_by_day[1] == {p.key for p in west} or keys_by_day[1] == {
            p.key for p in east
        }
        # 서로 다른 지리적 그룹이 서로 다른 day로 온전히 분리되어야 함
        assert len(keys_by_day[1]) == 4
        assert len(keys_by_day[2]) == 4
        assert keys_by_day[1] != keys_by_day[2]

    def test_all_places_assigned_no_loss(self):
        places = [
            PlaceCoord(f"p{i}", 33.0 + i * 0.01, 126.0 + i * 0.01) for i in range(10)
        ]

        result = cluster_by_day(places, num_days=3)

        assigned_keys = {p.key for day_places in result.values() for p in day_places}
        assert assigned_keys == {p.key for p in places}

    def test_tightly_clustered_places_still_fill_every_day(self):
        # 전부 같은 좌표에 몰려있으면 k-means 초기화 방식에 따라 빈 클러스터가
        # 생길 수 있는데, _fix_empty_clusters가 이를 채워 모든 day가 비지 않아야 함
        places = [PlaceCoord(f"p{i}", 33.0, 126.0) for i in range(6)]

        result = cluster_by_day(places, num_days=3)

        assert all(len(day_places) > 0 for day_places in result.values())
        assigned_keys = {p.key for day_places in result.values() for p in day_places}
        assert assigned_keys == {p.key for p in places}


class TestOrderWithinDay:
    def test_empty_and_single_place_unchanged(self):
        assert order_within_day([]) == []
        single = [PlaceCoord("a", 0, 0)]
        assert order_within_day(single) == single

    def test_brute_force_finds_optimal_square_perimeter(self):
        # 정사각형 네 꼭짓점: 대각선을 가로지르지 않는 둘레 순서가 최적해
        square = [
            PlaceCoord("A", 0, 0),
            PlaceCoord("C", 1, 1),
            PlaceCoord("B", 1, 0),
            PlaceCoord("D", 0, 1),
        ]

        ordered = order_within_day(square)

        assert [p.key for p in ordered][0] == "A"
        # 둘레를 도는 순서(A-B-C-D 혹은 A-D-C-B)여야 하며 대각선(A-C)으로 시작하면 안 됨
        assert {ordered[1].key, ordered[-1].key} == {"B", "D"}

    def test_greedy_fallback_visits_all_places_when_large(self):
        many = [PlaceCoord(f"p{i}", i * 0.01, i * 0.01) for i in range(9)]

        ordered = order_within_day(many)

        assert {p.key for p in ordered} == {p.key for p in many}
        assert len(ordered) == 9


class TestAssignTimeSlots:
    def test_empty_returns_empty(self):
        assert (
            assign_time_slots(
                [],
                is_first_day=True,
                is_last_day=True,
                arrival_time="MORNING",
                departure_time="EVENING",
            )
            == []
        )

    def test_first_day_excludes_slots_before_arrival(self):
        places = [PlaceCoord(f"p{i}", 0, 0) for i in range(3)]

        result = assign_time_slots(
            places,
            is_first_day=True,
            is_last_day=False,
            arrival_time="LUNCH",
            departure_time="EVENING",
        )

        slots_used = {slot for _, slot in result}
        assert "MORNING" not in slots_used

    def test_last_day_excludes_slots_after_departure(self):
        places = [PlaceCoord(f"p{i}", 0, 0) for i in range(3)]

        result = assign_time_slots(
            places,
            is_first_day=False,
            is_last_day=True,
            arrival_time="MORNING",
            departure_time="LUNCH",
        )

        slots_used = {slot for _, slot in result}
        assert "EVENING" not in slots_used

    def test_preserves_input_order(self):
        places = [PlaceCoord(f"p{i}", 0, 0) for i in range(6)]

        result = assign_time_slots(
            places,
            is_first_day=False,
            is_last_day=False,
            arrival_time="MORNING",
            departure_time="EVENING",
        )

        assert [p.key for p, _ in result] == [p.key for p in places]

    def test_all_items_assigned(self):
        places = [PlaceCoord(f"p{i}", 0, 0) for i in range(7)]

        result = assign_time_slots(
            places,
            is_first_day=False,
            is_last_day=False,
            arrival_time="MORNING",
            departure_time="EVENING",
        )

        assert len(result) == 7

    def test_single_day_trip_falls_back_to_arrival_slot_when_range_empty(self):
        # 방어적 분기: arrival이 departure보다 늦으면(정상 흐름에선 상위 검증이 막음)
        # 최소한 arrival_time 슬롯 하나로는 전부 배정되어야 함
        places = [PlaceCoord("a", 0, 0)]

        result = assign_time_slots(
            places,
            is_first_day=True,
            is_last_day=True,
            arrival_time="EVENING",
            departure_time="MORNING",
        )

        assert [slot for _, slot in result] == ["EVENING"]


class TestComputeStartTimes:
    def test_empty_returns_empty(self):
        assert compute_start_times([], []) == []

    def test_single_item_starts_at_slot_base(self):
        slotted = [(PlaceCoord("a", 0, 0), "MORNING")]

        result = compute_start_times(slotted, [None])

        assert result == ["09:00"]

    def test_accumulates_visit_and_travel_time_within_slot(self):
        slotted = [
            (PlaceCoord("a", 0, 0), "MORNING"),
            (PlaceCoord("b", 0, 0), "MORNING"),
        ]

        result = compute_start_times(slotted, [20, None])

        # 09:00 -> +90(체류) +20(이동) = 110분 후 -> 10:50
        assert result == ["09:00", "10:50"]

    def test_jumps_forward_to_next_slot_base_time(self):
        slotted = [
            (PlaceCoord("a", 0, 0), "MORNING"),
            (PlaceCoord("b", 0, 0), "EVENING"),
        ]

        result = compute_start_times(slotted, [10, None])

        assert result == ["09:00", "18:00"]
