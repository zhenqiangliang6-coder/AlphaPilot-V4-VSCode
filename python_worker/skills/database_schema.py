from .base import Skill


def register(registry):
    registry.register(
        Skill(
            id="database.schema",
            name="Database Schema Management",
            version="1.0.0",
            description="Guidance for PostgreSQL/pgvector schema design, migrations, and database operations.",
            triggers=(
                "database",
                "sql",
                "migration",
                "schema",
                "table",
                "postgresql",
                "postgres",
                "pgvector",
                "数据库",
                "SQL",
                "迁移",
                "表结构",
                "数据库设计",
                "索引",
                "foreign key",
            ),
            priority=140,
            capabilities=("workspace.read", "schema.propose", "migration.propose"),
            guidance=(
                "For database work, use PostgreSQL with pgvector for vector similarity search. "
                "Follow migration best practices: use versioned migration files, maintain backward compatibility, "
                "provide rollback plans, and avoid data loss. Use appropriate indexes (B-tree, GIN, HNSW for pgvector). "
                "Define foreign keys for referential integrity, use transactions for schema changes, "
                "and validate constraints before production deployment. "
                "For pgvector, use HNSW indexes for large vector tables, set appropriate ef_construction and M parameters. "
                "This skill only proposes schema changes: actual migration execution requires host authorization."
            ),
        )
    )
