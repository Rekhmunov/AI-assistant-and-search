from app.models.broadcast import BroadcastAudience, BroadcastLogStatus, BroadcastStatus


def test_broadcast_enum_values_match_postgres():
    assert BroadcastAudience.ALL.value == "all"
    assert BroadcastAudience.FREE.value == "free"
    assert BroadcastAudience.PRO.value == "pro"
    assert BroadcastStatus.DRAFT.value == "draft"
    assert BroadcastStatus.SENDING.value == "sending"
    assert BroadcastStatus.DONE.value == "done"
    assert BroadcastStatus.FAILED.value == "failed"
    assert BroadcastLogStatus.SENT.value == "sent"
    assert BroadcastLogStatus.FAILED.value == "failed"
