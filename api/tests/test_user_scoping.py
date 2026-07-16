"""D6: user_scoped() is the mandatory query path for user-owned tables."""

import pytest

from palio.db.base import user_scoped
from palio.db.models import Pattern, PatternType, ReferralEntry

pytestmark = pytest.mark.pg


def test_user_scoped_isolates_rows(session, make_user):
    alice, bob = make_user(), make_user()
    session.add_all(
        [
            Pattern(user_id=alice.id, type=PatternType.trigger, text="mornings before deadlines"),
            Pattern(user_id=bob.id, type=PatternType.strength, text="strong starter"),
        ]
    )
    session.flush()

    alice_rows = session.execute(user_scoped(Pattern, alice.id)).scalars().all()
    assert [p.user_id for p in alice_rows] == [alice.id]
    assert all("starter" not in p.text for p in alice_rows)


def test_user_scoped_rejects_global_tables():
    import uuid

    with pytest.raises(TypeError, match="no user_id column"):
        user_scoped(ReferralEntry, uuid.uuid4())
