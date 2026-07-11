import pytest

from app.llm_utils import parse_json_response, strip_code_fence


def test_plain_json_passthrough():
    assert strip_code_fence('{"a": 1}') == '{"a": 1}'


def test_strips_json_tagged_fence():
    text = '```json\n{"a": 1}\n```'
    assert strip_code_fence(text) == '{"a": 1}'


def test_strips_bare_fence():
    text = '```\n{"a": 1}\n```'
    assert strip_code_fence(text) == '{"a": 1}'


def test_strips_surrounding_whitespace():
    text = '\n\n  ```json\n{"a": 1}\n```  \n'
    assert strip_code_fence(text) == '{"a": 1}'


def test_parse_json_response_handles_fenced_output():
    text = '```json\n{"a": 1, "b": [1, 2]}\n```'
    assert parse_json_response(text) == {"a": 1, "b": [1, 2]}


def test_parse_json_response_raises_on_garbage():
    with pytest.raises(Exception):
        parse_json_response("이건 JSON이 아님")
