from typing import List, Optional

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Batch(Base):
    __tablename__ = "batches"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    date: Mapped[Optional[str]] = mapped_column(String)  # e.g. "Winter 2024"

    teams: Mapped[List["Team"]] = relationship(back_populates="batch", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Batch(name='{self.name}')>"

    def __str__(self):
        return self.name


class Team(Base):
    __tablename__ = "teams"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String, index=True, nullable=False)
    batch_id: Mapped[int] = mapped_column(ForeignKey("batches.id"), nullable=False)

    batch: Mapped["Batch"] = relationship(back_populates="teams")
    members: Mapped[List["Member"]] = relationship(back_populates="team", cascade="all, delete-orphan")

    __table_args__ = (UniqueConstraint("name", "batch_id", name="_team_batch_uc"),)

    def __repr__(self):
        return f"<Team(name='{self.name}', batch='{self.batch.name if self.batch else 'N/A'}')>"

    def __str__(self):
        return f"{self.name} ({self.batch.name if self.batch else 'No Batch'})"


class Member(Base):
    __tablename__ = "members"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String, index=True, nullable=False)
    gitlab_username: Mapped[str] = mapped_column(String, unique=True, index=True, nullable=False)
    gitlab_email: Mapped[Optional[str]] = mapped_column(String, unique=True, index=True)
    corpus_username: Mapped[Optional[str]] = mapped_column(String, index=True)
    global_username: Mapped[Optional[str]] = mapped_column(String, index=True)
    global_email: Mapped[Optional[str]] = mapped_column(String, index=True)
    date_of_joining: Mapped[Optional[str]] = mapped_column(String)
    college_name: Mapped[Optional[str]] = mapped_column(String)

    team_id: Mapped[Optional[int]] = mapped_column(ForeignKey("teams.id"))
    team: Mapped[Optional["Team"]] = relationship(back_populates="members")

    def __repr__(self):
        return f"<Member(name='{self.name}', username='{self.gitlab_username}')>"

    def __str__(self):
        return f"{self.name} (@{self.gitlab_username})"
