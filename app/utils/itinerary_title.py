from datetime import date


def generate_itinerary_title(region: str, start_date: date, end_date: date) -> str:
    nights = (end_date - start_date).days
    if nights == 0:
        return f"{region} 당일치기"
    return f"{region} {nights}박{nights + 1}일"
