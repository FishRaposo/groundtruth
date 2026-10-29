"""Optional pgvector type, imported only by an actual PostgreSQL dialect."""

from sqlalchemy import JSON
from sqlalchemy.types import TypeDecorator


class Vector384(TypeDecorator):
    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect):
        if dialect.name == "postgresql":
            from pgvector.sqlalchemy import Vector

            return dialect.type_descriptor(Vector(384))
        return dialect.type_descriptor(JSON())
