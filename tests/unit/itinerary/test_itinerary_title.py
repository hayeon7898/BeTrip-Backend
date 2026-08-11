from datetime import date

from app.utils.itinerary_title import generate_itinerary_title


def test_generate_title_multi_day_trip():
    title = generate_itinerary_title("제주도", date(2026, 8, 10), date(2026, 8, 13))
    assert title == "제주도 3박4일"


def test_generate_title_single_night_trip():
    title = generate_itinerary_title("전주", date(2026, 9, 1), date(2026, 9, 2))
    assert title == "전주 1박2일"


def test_generate_title_day_trip():
    title = generate_itinerary_title("부산", date(2026, 10, 5), date(2026, 10, 5))
    assert title == "부산 당일치기"
