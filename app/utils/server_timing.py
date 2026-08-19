def format_server_timing(
    timings: dict[str, float], descriptions: dict[str, str] | None = None
) -> str:
    """
    (개발용)
    dict를 표준 HTTP `Server-Timing` 헤더 값으로 변환한다.
    이 헤더가 응답에 실려 있으면 Chrome 개발자도구에서
    Network 탭 > 요청 클릭 > Timing 패널에 항목별 소요시간이 막대그래프로 자동 표시된다.

    descriptions에 같은 key가 있으면 `;desc="..."`로 덧붙는다
    부가 정보를 실어서 Response Headers에서 읽을 수 있도록 하기 위함.
    """
    descriptions = descriptions or {}
    parts = []
    for name, duration in timings.items():
        entry = f"{name};dur={duration:.1f}"
        if name in descriptions:
            entry += f';desc="{descriptions[name]}"'
        parts.append(entry)
    return ", ".join(parts)
