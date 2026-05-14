from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from internship_activity_tracker.infrastructure.database import Base
from internship_activity_tracker.services import roster_service


@pytest.fixture
def db_session():
    # Use in-memory SQLite for tests
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()

    # Patch the get_session to return our test session
    # roster_service uses get_session() which is a context manager
    from contextlib import contextmanager

    @contextmanager
    def mock_get_session():
        yield session
        session.commit()

    with pytest.MonkeyPatch().context() as mp:
        mp.setattr("internship_activity_tracker.services.roster_service.get_session", mock_get_session)
        yield session

    session.close()
    Base.metadata.drop_all(engine)


def test_add_batch(db_session):
    batch = roster_service.add_batch("Batch 1", "2024-01-01")
    assert batch.id is not None
    assert batch.name == "Batch 1"

    batches = roster_service.get_all_batches()
    assert len(batches) > 0
    assert batches[0]["name"] == "Batch 1"


def test_add_or_update_member(db_session):
    batch = roster_service.add_batch("Batch A", "2024-01-01")
    data = {
        "team_name": "Team 1",
        "name": "John Doe",
        "gitlab_username": "jdoe",
        "gitlab_email": "jdoe@example.com",
    }
    roster_service.add_or_update_member(db_session, data, batch.id)

    member = roster_service.get_member_by_username("jdoe")
    assert member is not None
    assert member["name"] == "John Doe"
    assert member["team_name"] == "Team 1"


def test_is_member_registered(db_session):
    batch = roster_service.add_batch("Batch B", "2024-01-01")
    data = {
        "gitlab_username": "registered_user",
        "name": "Registered",
    }
    roster_service.add_or_update_member(db_session, data, batch.id)

    assert roster_service.is_member_registered("registered_user") is True
    assert roster_service.is_member_registered("REGistered_USER") is True  # Case insensitive
    assert roster_service.is_member_registered("unknown") is False


def test_get_member_by_id(db_session):
    batch = roster_service.add_batch("Batch C", "2024-01-01")
    data = {"gitlab_username": "user_id_test", "name": "ID Test"}
    roster_service.add_or_update_member(db_session, data, batch.id)

    # We need to get the actual ID from the DB
    from internship_activity_tracker.infrastructure.models import Member

    m = db_session.query(Member).filter_by(gitlab_username="user_id_test").first()

    retrieved = roster_service.get_member_by_id(m.id)
    assert retrieved["name"] == "ID Test"
    assert roster_service.get_member_by_id(9999) is None


def test_get_all_members_with_teams_multiple(db_session):
    batch = roster_service.add_batch("Batch D", "2024-01-01")
    roster_service.add_or_update_member(
        db_session, {"gitlab_username": "u1", "name": "N1", "team_name": "T1"}, batch.id
    )
    roster_service.add_or_update_member(
        db_session, {"gitlab_username": "u2", "name": "N2", "team_name": "T1"}, batch.id
    )

    members = roster_service.get_all_members_with_teams()
    assert len(members) == 2


def test_delete_member(db_session):
    batch = roster_service.add_batch("Batch E", "2024-01-01")
    roster_service.add_or_update_member(db_session, {"gitlab_username": "del_me", "name": "Bye"}, batch.id)

    from internship_activity_tracker.infrastructure.models import Member

    m = db_session.query(Member).filter_by(gitlab_username="del_me").first()

    roster_service.delete_member(m.id)
    assert roster_service.get_member_by_id(m.id) is None


def test_get_all_teams_with_members(db_session):
    batch = roster_service.add_batch("Batch F", "2024-01-01")
    roster_service.add_or_update_member(
        db_session, {"gitlab_username": "u1", "name": "N1", "team_name": "Team Alpha"}, batch.id
    )

    teams = roster_service.get_all_teams_with_members()
    assert len(teams) == 1
    assert teams[0]["team_name"] == "Team Alpha"
    assert len(teams[0]["members"]) == 1


def test_get_all_teams(db_session):
    batch = roster_service.add_batch("Batch G", "2024-01-01")
    roster_service.add_or_update_member(
        db_session, {"gitlab_username": "u1", "name": "N1", "team_name": "Team Beta"}, batch.id
    )

    team_names = roster_service.get_all_teams()
    assert "Team Beta" in team_names


def test_get_teams_by_batch(db_session):
    batch = roster_service.add_batch("Batch H", "2024-01-01")
    roster_service.add_or_update_member(
        db_session, {"gitlab_username": "u1", "name": "N1", "team_name": "T-H"}, batch.id
    )

    teams = roster_service.get_teams_by_batch("Batch H")
    assert len(teams) == 1
    assert teams[0]["name"] == "T-H"

    all_teams = roster_service.get_teams_by_batch("All Batches")
    assert len(all_teams) >= 1


def test_get_members_by_team(db_session):
    batch = roster_service.add_batch("Batch I", "2024-01-01")
    roster_service.add_or_update_member(
        db_session, {"gitlab_username": "u-i", "name": "N-I", "team_name": "T-I"}, batch.id
    )

    members = roster_service.get_members_by_team("T-I", "Batch I")
    assert len(members) == 1
    assert members[0]["gitlab_username"] == "u-i"


def test_bulk_import_members(db_session):
    batch = roster_service.add_batch("Batch J", "2024-01-01")
    csv_content = b"Name,GitLab Username,Team Name\nJohn,johndoe,Team J"

    with patch("internship_activity_tracker.services.weekly_performance.models.parse_intern_csv") as mock_parse:
        mock_parse.return_value = [{"name": "John", "gitlab_username": "johndoe", "team_name": "Team J"}]
        count, errors = roster_service.bulk_import_members(csv_content, batch.id)

    assert count == 1
    assert len(errors) == 0
    assert roster_service.is_member_registered("johndoe")


def test_bulk_import_members_empty(db_session):
    batch = roster_service.add_batch("Batch K", "2024-01-01")
    count, errors = roster_service.bulk_import_members(b"", batch.id)
    assert count == 0
    assert "No valid records" in errors[0]
