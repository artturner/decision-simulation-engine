"""
SQLAlchemy declarative base.

All ORM model classes must inherit from ``Base`` defined here so that
``Base.metadata`` contains every table and Alembic can auto-generate
migrations.

Import order matters: import this module *before* any model modules so
that the metadata is fully populated when ``alembic env.py`` imports it.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Project-wide declarative base for all SQLAlchemy models."""
