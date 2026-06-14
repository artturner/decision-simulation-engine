from __future__ import annotations

import enum
import secrets
import string
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum as SAEnum, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


JOIN_CODE_ALPHABET = string.ascii_uppercase + string.digits


def generate_join_code() -> str:
    """Return a short, human-readable class code."""
    return "".join(secrets.choice(JOIN_CODE_ALPHABET) for _ in range(6))


class UserRole(str, enum.Enum):
    teacher = "teacher"
    admin = "admin"


class User(Base):
    """A teacher or site admin account.

    Identity is managed by Supabase Auth; this row is created on first
    login using the subject claim from the JWT as the primary key so the
    two systems share the same UUID without a separate lookup table.
    """

    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        comment="Matches the Supabase Auth user UUID (sub claim)",
    )
    email: Mapped[str] = mapped_column(
        String(500),
        unique=True,
        nullable=False,
        index=True,
    )
    role: Mapped[UserRole] = mapped_column(
        SAEnum(UserRole, name="userrole", create_type=True),
        nullable=False,
        default=UserRole.teacher,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    class_rolls: Mapped[list[ClassRoll]] = relationship(
        "ClassRoll",
        back_populates="owner",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r} role={self.role.value!r}>"


class ClassRoll(Base):
    """A reusable list of student names owned by a teacher.

    One roll can be assigned to many scenarios via ScenarioRollAssignment.
    When a student enters a play through the class picker, their name is
    validated against this list server-side.
    """

    __tablename__ = "class_rolls"

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
        comment='Display name, e.g. "Period 3, Spring 2026"',
    )
    join_code: Mapped[str] = mapped_column(
        String(16),
        unique=True,
        nullable=False,
        index=True,
        default=generate_join_code,
        comment="Student-facing class code used on /join",
    )
    student_names: Mapped[list] = mapped_column(
        JSONB,
        nullable=False,
        default=list,
        comment='Ordered list of canonical student names, e.g. ["Last, First", ...]',
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    owner: Mapped[User] = relationship("User", back_populates="class_rolls")
    assignments: Mapped[list[ScenarioRollAssignment]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        "ScenarioRollAssignment",
        back_populates="class_roll",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<ClassRoll id={self.id} name={self.name!r}>"
