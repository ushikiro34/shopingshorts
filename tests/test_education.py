from app.discovery.education import detect_needs_education


def test_detects_keyword_in_category():
    assert detect_needs_education("자외선차단제", "썬크림 50g") is True


def test_detects_keyword_in_product_name():
    assert detect_needs_education("생활용품", "정수 필터 카트리지") is True


def test_no_match_returns_false():
    assert detect_needs_education("생활용품", "휴지") is False


def test_handles_none_values():
    assert detect_needs_education(None, None) is False
