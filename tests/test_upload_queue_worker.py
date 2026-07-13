from datetime import datetime, timedelta, timezone

from app.upload.queue_worker import promote_ready_items


class _FakeQuery:
    def __init__(self, rows: list[dict], op: str, payload=None):
        self.rows = rows
        self.op = op
        self.payload = payload
        self.filters: list[tuple[str, str, object]] = []

    def eq(self, col, val):
        self.filters.append(("eq", col, val))
        return self

    def lte(self, col, val):
        self.filters.append(("lte", col, val))
        return self

    def select(self, *_args):
        return self

    def _matches(self, row) -> bool:
        for kind, col, val in self.filters:
            if kind == "eq" and row.get(col) != val:
                return False
            if kind == "lte" and row.get(col) > val:
                return False
        return True

    def execute(self):
        if self.op == "select":
            data = [r for r in self.rows if self._matches(r)]
            return type("Result", (), {"data": data})()
        if self.op == "update":
            for r in self.rows:
                if self._matches(r):
                    r.update(self.payload)
            return type("Result", (), {"data": [r for r in self.rows if self._matches(r)]})()
        raise NotImplementedError(self.op)


class FakeUploadQueueClient:
    """upload_queue 테이블만 흉내내는 최소 fake — promote_ready_items 검증용."""

    def __init__(self, rows: list[dict]):
        self.rows = rows

    def table(self, name):
        assert name == "upload_queue"
        return self

    def select(self, *_args):
        return _FakeQuery(self.rows, "select")

    def update(self, payload):
        return _FakeQuery(self.rows, "update", payload)


def _iso(delta_minutes: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=delta_minutes)).isoformat()


def test_promote_ready_items_only_promotes_past_ready_at():
    rows = [
        {"id": "past", "status": "pending_review", "ready_at": _iso(-10)},
        {"id": "future", "status": "pending_review", "ready_at": _iso(60)},
        {"id": "already_published", "status": "published", "ready_at": _iso(-100)},
    ]
    client = FakeUploadQueueClient(rows)

    promoted = promote_ready_items(client=client)

    assert promoted == ["past"]
    by_id = {r["id"]: r for r in rows}
    assert by_id["past"]["status"] == "ready_to_publish"
    assert by_id["future"]["status"] == "pending_review"
    assert by_id["already_published"]["status"] == "published"


def test_promote_ready_items_returns_empty_when_nothing_ready():
    rows = [{"id": "future", "status": "pending_review", "ready_at": _iso(60)}]
    client = FakeUploadQueueClient(rows)

    promoted = promote_ready_items(client=client)

    assert promoted == []
    assert rows[0]["status"] == "pending_review"


def test_promote_ready_items_never_touches_status_besides_pending_review():
    # canceled/failed 등 다른 상태는 ready_at이 지났어도 절대 건드리지 않는다.
    rows = [{"id": "canceled_but_old", "status": "canceled", "ready_at": _iso(-1000)}]
    client = FakeUploadQueueClient(rows)

    promoted = promote_ready_items(client=client)

    assert promoted == []
    assert rows[0]["status"] == "canceled"
