"""GET /api/tasks 테스트."""

from __future__ import annotations


def test_tasks_endpoint_returns_pool(client):
    resp = client.get("/api/tasks")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) == 12  # 풀 크기 확장 확인
    ids = {t["id"] for t in body}
    assert {
        "translate-positive",
        "extract-number",
        "classify-sentiment",
        "to-uppercase",
        "count-vowels",
        "json-keys",
        # 신규 추가 문제
        "reverse-string",
        "palindrome-check",
        "roman-to-int",
        "sql-injection-detect",
    }.issubset(ids)

    sample = body[0]
    # 정답 데이터는 노출하면 안 된다
    assert "test_cases" not in sample
    assert "expected" not in sample
    # 필수 메타데이터
    assert {"id", "description", "model", "total_count"} <= set(sample.keys())
    assert sample["total_count"] >= 1
