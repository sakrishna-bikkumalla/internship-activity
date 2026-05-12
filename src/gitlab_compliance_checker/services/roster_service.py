from typing import List

from sqlalchemy.orm import Session

from ..infrastructure.database import get_session
from ..infrastructure.models import Batch, Member, Team
from .weekly_performance.models import InternCSVRow


def get_all_batches() -> List[dict]:
    """Fetches all batches from the database."""
    with get_session() as session:
        batches = session.query(Batch).all()
        return [{"id": b.id, "name": b.name, "date": b.date} for b in batches]


def add_batch(name: str, date: str) -> Batch:
    """Creates a new batch."""
    with get_session() as session:
        batch = Batch(name=name, date=date)
        session.add(batch)
        session.commit()
        session.refresh(batch)
        return batch


def get_all_members_with_teams() -> List[InternCSVRow]:
    """Fetches all members and their team names from the database."""
    with get_session() as session:
        members = session.query(Member).all()
        result: List[InternCSVRow] = []
        for m in members:
            result.append(
                {
                    "id": m.id,
                    "batch_name": m.team.batch.name if m.team and m.team.batch else "No Batch",
                    "team_name": m.team.name if m.team else "No Team",
                    "name": m.name,
                    "gitlab_username": m.gitlab_username,
                    "gitlab_email": m.gitlab_email or "",
                    "corpus_username": m.corpus_username or "",
                    "global_username": m.global_username or "",
                    "global_email": m.global_email or "",
                    "date_of_joining": m.date_of_joining or "",
                    "college_name": m.college_name or "",
                }
            )
        return result


def is_member_registered(gitlab_username: str) -> bool:
    """Checks if a GitLab username exists in the Member table (case-insensitive)."""
    with get_session() as session:
        member = session.query(Member).filter(Member.gitlab_username.ilike(gitlab_username)).first()
        return member is not None


def get_member_by_id(member_id: int) -> dict | None:
    """Fetches a single member's details by their database ID."""
    with get_session() as session:
        m = session.query(Member).get(member_id)
        if not m:
            return None
        return {
            "id": m.id,
            "name": m.name,
            "gitlab_username": m.gitlab_username,
            "gitlab_email": m.gitlab_email,
            "corpus_username": m.corpus_username,
            "global_username": m.global_username,
            "global_email": m.global_email,
            "date_of_joining": m.date_of_joining,
            "college_name": m.college_name,
            "team_name": m.team.name if m.team else "No Team",
            "team_id": m.team_id,
            "batch_id": m.team.batch_id if m.team else None,
        }


def get_member_by_username(gitlab_username: str) -> InternCSVRow | None:
    """Fetches a single member's details by their GitLab username."""
    with get_session() as session:
        m = session.query(Member).filter(Member.gitlab_username.ilike(gitlab_username)).first()
        if not m:
            return None
        return {
            "team_name": m.team.name if m.team else "No Team",
            "name": m.name,
            "gitlab_username": m.gitlab_username,
            "gitlab_email": m.gitlab_email or "",
            "corpus_username": m.corpus_username or "",
            "global_username": m.global_username or "",
            "global_email": m.global_email or "",
            "date_of_joining": m.date_of_joining or "",
            "college_name": m.college_name or "",
        }


def get_all_teams_with_members() -> List[dict]:
    """Fetches all teams and their members from the database in a format compatible with Batch Analytics."""
    with get_session() as session:
        teams = session.query(Team).all()
        result = []
        for t in teams:
            result.append(
                {
                    "team_name": t.name,
                    "batch_name": t.batch.name if t.batch else "No Batch",
                    "project_name": "",  # Project name could be added to Team model if needed
                    "members": [
                        {
                            "name": m.name,
                            "username": m.gitlab_username,
                            "corpus_username": m.corpus_username or "",
                            "global_username": m.global_username,
                            "global_email": m.global_email,
                            "date_of_joining": m.date_of_joining,
                        }
                        for m in t.members
                    ],
                    "scope": "all",
                }
            )
        return result


def get_all_teams() -> List[str]:
    """Fetches all team names from the database."""
    with get_session() as session:
        return [t.name for t in session.query(Team).all()]


def get_teams_by_batch(batch_name: str) -> List[dict]:
    """Fetches all teams belonging to a specific batch."""
    with get_session() as session:
        if batch_name == "All Batches":
            teams = session.query(Team).all()
        else:
            teams = session.query(Team).join(Batch).filter(Batch.name == batch_name).all()

        return [
            {
                "id": t.id,
                "name": t.name,
                "batch_name": t.batch.name if t.batch else "No Batch",
            }
            for t in teams
        ]


def get_members_by_team(team_name: str, batch_name: str = "All Batches") -> List[dict]:
    """Fetches all members belonging to a specific team (within a batch context)."""
    with get_session() as session:
        query = session.query(Member).join(Team)
        if batch_name != "All Batches":
            query = query.join(Batch).filter(Batch.name == batch_name)

        members = query.filter(Team.name == team_name).all()
        return [
            {
                "id": m.id,
                "name": m.name,
                "gitlab_username": m.gitlab_username,
                "team_name": m.team.name if m.team else "No Team",
            }
            for m in members
        ]


def add_or_update_member(session: Session, data: InternCSVRow, batch_id: int, member_id: int | None = None):
    """Adds a new member or updates an existing one within a specific batch."""
    team_name = data.get("team_name", "Default Team")
    # Lookup team within the specific batch
    team = session.query(Team).filter_by(name=team_name, batch_id=batch_id).first()
    if not team:
        team = Team(name=team_name, batch_id=batch_id)
        session.add(team)
        session.flush()

    if not data.get("gitlab_username"):
        raise ValueError("GitLab username is required.")

    member = None
    if member_id:
        member = session.query(Member).get(member_id)

    if not member:
        member = session.query(Member).filter_by(gitlab_username=data["gitlab_username"]).first()

    if not member:
        member = Member(gitlab_username=data["gitlab_username"])
        session.add(member)

    member.name = data.get("name", member.name)
    member.gitlab_username = data.get("gitlab_username", member.gitlab_username)
    member.gitlab_email = data.get("gitlab_email", member.gitlab_email)
    member.corpus_username = data.get("corpus_username", member.corpus_username)
    member.global_username = data.get("global_username", member.global_username)
    member.global_email = data.get("global_email", member.global_email)
    member.date_of_joining = data.get("date_of_joining", member.date_of_joining)
    member.college_name = data.get("college_name", member.college_name)
    member.team_id = team.id


def delete_member(member_id: int) -> bool:
    """Deletes a member from the database. Returns True if deleted, False if not found."""
    with get_session() as session:
        member = session.query(Member).get(member_id)
        if member:
            session.delete(member)
            session.commit()
            return True
        return False


def bulk_import_members(csv_content: bytes, batch_id: int) -> tuple[int, list[str]]:
    """
    Parses CSV and imports members into a specific batch.
    Returns a tuple containing the number of successful imports and a list of error messages.
    """
    import logging

    from .weekly_performance.models import parse_intern_csv

    rows = parse_intern_csv(csv_content)
    if not rows:
        return 0, ["No valid records found in the CSV or empty file."]

    errors = []
    with get_session() as session:
        count = 0
        for i, row in enumerate(rows, start=1):
            try:
                add_or_update_member(session, row, batch_id)
                # Flush immediately to catch database constraint errors like UniqueViolation on this specific row
                session.flush()
                count += 1
            except Exception as e:
                session.rollback()
                error_str = str(e)
                if "UniqueViolation" in error_str or "duplicate key value" in error_str:
                    msg = f"Upload terminated at Row {i} (User: {row.get('gitlab_username', 'Unknown')}): A duplicate entry exists (likely the GitLab email or username)."
                else:
                    msg = f"Upload terminated at Row {i} (User: {row.get('gitlab_username', 'Unknown')}): {error_str}"

                logging.error(f"Failed to import row {row}: {e}")
                errors.append(msg)
                # Terminate the upload completely, returning 0 successful imports
                return 0, errors

        # If all rows succeed, commit the entire batch
        session.commit()
        return count, errors
