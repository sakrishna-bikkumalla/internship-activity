from internship_activity_tracker.infrastructure.gitlab.parsers import parse_json, parse_yaml


def test_parse_yaml_valid():
    content = "key: value\nlist:\n  - item1\n  - item2"
    result = parse_yaml(content)
    assert result == {"key": "value", "list": ["item1", "item2"]}


def test_parse_yaml_invalid():
    content = "key: : value"  # Invalid YAML
    result = parse_yaml(content)
    assert result is None


def test_parse_yaml_empty():
    assert parse_yaml("") is None
    assert parse_yaml(None) is None


def test_parse_json_valid():
    content = '{"key": "value", "list": ["item1", "item2"]}'
    result = parse_json(content)
    assert result == {"key": "value", "list": ["item1", "item2"]}


def test_parse_json_invalid():
    content = '{"key": "value",}'  # Invalid JSON (trailing comma)
    result = parse_json(content)
    assert result is None


def test_parse_json_empty():
    assert parse_json("") is None
    assert parse_json(None) is None
