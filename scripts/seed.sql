-- 로컬 개발/데모용 시드 데이터.

-- 실행: psql -U postgres -d betrip -f scripts/seed.sql
-- (DATABASE_URL은 .env 참고. 이미 존재하는 행은 건드리지 않음 — 여러 번 실행해도 안전)

-- 로그인 정보: openapi@example.com / 2026openapi!
-- POST /api/v1/auth/login 으로 로그인 후 access_token을 Swagger Authorize에 넣고 테스트할 것.

-- 1. 테스트 유저
INSERT INTO users (user_id, email, password_hash, nickname, provider)
VALUES (
    '66666666-6666-6666-6666-666666666666',
    'openapi@example.com',
    '$2b$12$VHSadpL4ASu1G2a35hV5c.Th06XBn/RLYsFPG2vnEZROcrfqY2EpK',
    '테스트유저',
    'LOCAL'
)
ON CONFLICT (email) DO NOTHING;

-- 2. 장소 (실좌표 — 부산/제주)
INSERT INTO places (place_id, name, category, address, lat, lng, place_url)
VALUES
    ('kakao-busan-haeundae', '해운대해수욕장', 'ACTIVITY', '부산 해운대구 우동', 35.1585232, 129.1598547, 'https://place.map.kakao.com/busan-haeundae'),
    ('kakao-busan-gwangalli', '광안리해수욕장', 'ACTIVITY', '부산 수영구 광안동', 35.1531, 129.1186, 'https://place.map.kakao.com/busan-gwangalli'),
    ('kakao-busan-jagalchi', '자갈치시장', 'RESTAURANT', '부산 중구 자갈치해안로', 35.0968, 129.0306, 'https://place.map.kakao.com/busan-jagalchi'),
    ('kakao-busan-gukje', '국제시장', 'ACTIVITY', '부산 중구 신창동', 35.1003, 129.0294, 'https://place.map.kakao.com/busan-gukje'),
    ('kakao-busan-jeonpo', '전포카페거리', 'CAFE', '부산 부산진구 전포동', 35.1571, 129.0632, 'https://place.map.kakao.com/busan-jeonpo'),
    ('kakao-busan-gamcheon', '감천문화마을', 'ACTIVITY', '부산 사하구 감천동', 35.0975, 129.0107, 'https://place.map.kakao.com/busan-gamcheon'),
    ('kakao-12345', '협재해수욕장', 'ACTIVITY', '제주시 한림읍', 33.3938, 126.2397, 'https://place.map.kakao.com/12345'),
    ('kakao-jeju-seongsan', '성산일출봉', 'ACTIVITY', '제주 서귀포시 성산읍', 33.4586, 126.9425, 'https://place.map.kakao.com/jeju-seongsan'),
    ('kakao-jeju-heukdwaeji', '흑돼지거리', 'RESTAURANT', '제주시 노형동', 33.4890, 126.4983, 'https://place.map.kakao.com/jeju-heukdwaeji'),
    ('kakao-jeju-dongmun', '동문시장', 'RESTAURANT', '제주시 이도1동', 33.5141, 126.5292, 'https://place.map.kakao.com/jeju-dongmun'),
    ('kakao-67890', '제주국제공항', 'ACTIVITY', '제주시 용담2동', 33.5066, 126.4930, 'https://place.map.kakao.com/67890')
ON CONFLICT (place_id) DO NOTHING;

-- 3. 예정된 여행 — 부산 2박3일 (SAVED, 완성된 일정표)
INSERT INTO itineraries (
    itinerary_id, user_id, title, status, region,
    start_date, end_date, arrival_time, departure_time,
    transportation, purpose, styles
)
VALUES (
    '77777777-7777-7777-7777-777777777777',
    '66666666-6666-6666-6666-666666666666',
    '부산 2박3일', 'SAVED', '부산',
    '2026-10-10', '2026-10-12', 'MORNING', 'EVENING',
    'CAR', 'FRIEND', '["ACTIVITY", "FOOD"]'
)
ON CONFLICT (itinerary_id) DO NOTHING;

INSERT INTO itinerary_places (itinerary_place_id, itinerary_id, place_id, day, time_slot, order_in_day, start_time, travel_time_to_next_min)
VALUES
    ('a1111111-1111-1111-1111-111111111111', '77777777-7777-7777-7777-777777777777', 'kakao-busan-haeundae', 1, 'MORNING', 1, '09:00', 15),
    ('a1111111-1111-1111-1111-111111111112', '77777777-7777-7777-7777-777777777777', 'kakao-busan-jeonpo',   1, 'LUNCH',   1, '12:00', 20),
    ('a1111111-1111-1111-1111-111111111113', '77777777-7777-7777-7777-777777777777', 'kakao-busan-jagalchi', 1, 'EVENING', 1, '18:00', NULL),
    ('a1111111-1111-1111-1111-111111111114', '77777777-7777-7777-7777-777777777777', 'kakao-busan-gwangalli',2, 'MORNING', 1, '09:30', 25),
    ('a1111111-1111-1111-1111-111111111115', '77777777-7777-7777-7777-777777777777', 'kakao-busan-gukje',    2, 'LUNCH',   1, '12:30', NULL),
    ('a1111111-1111-1111-1111-111111111116', '77777777-7777-7777-7777-777777777777', 'kakao-busan-gamcheon', 3, 'MORNING', 1, '10:00', NULL)
ON CONFLICT (itinerary_id, place_id) DO NOTHING;

-- 4. 지난 여행 — 제주 2박3일 (SAVED, 완성된 일정표)
INSERT INTO itineraries (
    itinerary_id, user_id, title, status, region,
    start_date, end_date, arrival_time, departure_time,
    transportation, purpose, styles
)
VALUES (
    '88888888-8888-8888-8888-888888888888',
    '66666666-6666-6666-6666-666666666666',
    '제주 2박3일', 'SAVED', '제주',
    '2026-08-14', '2026-08-16', 'LUNCH', 'EVENING',
    'PUBLIC_TRANSPORT', 'FAMILY', '["NATURE", "FOOD"]'
)
ON CONFLICT (itinerary_id) DO NOTHING;

INSERT INTO itinerary_places (itinerary_place_id, itinerary_id, place_id, day, time_slot, order_in_day, start_time, travel_time_to_next_min)
VALUES
    ('a2222222-2222-2222-2222-222222222221', '88888888-8888-8888-8888-888888888888', 'kakao-12345',           1, 'LUNCH',   1, '13:00', 40),
    ('a2222222-2222-2222-2222-222222222222', '88888888-8888-8888-8888-888888888888', 'kakao-jeju-heukdwaeji', 1, 'EVENING', 1, '18:30', NULL),
    ('a2222222-2222-2222-2222-222222222223', '88888888-8888-8888-8888-888888888888', 'kakao-jeju-seongsan',   2, 'MORNING', 1, '09:00', 35),
    ('a2222222-2222-2222-2222-222222222224', '88888888-8888-8888-8888-888888888888', 'kakao-jeju-dongmun',    2, 'LUNCH',   1, '13:30', NULL)
ON CONFLICT (itinerary_id, place_id) DO NOTHING;
