"""
RED: Write the failing test first.
Tests for src/db/schema.sql — verifies all required tables exist with correct columns.

Since we're testing SQL schema files, we verify the file content directly.
For actual DB tests, see tests/integration/test_db_adapter.py
"""
import pytest
import re


class TestSchemaFile:
    """Tests that the schema.sql file contains all required tables and columns."""

    def test_schema_file_exists(self):
        """The schema.sql file must exist in src/db/ directory."""
        import os
        schema_path = os.path.join(
            os.path.dirname(__file__),
            "..", "..", "src", "db", "schema.sql"
        )
        assert os.path.exists(schema_path), \
            f"schema.sql not found at {schema_path}"

    def test_campaigns_table_exists(self):
        """The campaigns table must define all required columns."""
        import os
        schema_path = os.path.join(
            os.path.dirname(__file__),
            "..", "..", "src", "db", "schema.sql"
        )
        with open(schema_path) as f:
            content = f.read()

        # Must contain campaigns table definition
        assert "CREATE TABLE" in content and "campaigns" in content.lower(), \
            "schema.sql must contain a campaigns table"

        # Required columns
        required_cols = [
            "id", "campaign_id", "customer_id", "name",
            "api_key_token", "status", "created_at"
        ]
        for col in required_cols:
            assert col in content, \
                f"campaigns table must have column: {col}"

    def test_wiki_entries_table_has_full_text_search(self):
        """The wiki_entries table must have PostgreSQL full-text search support."""
        import os
        schema_path = os.path.join(
            os.path.dirname(__file__),
            "..", "..", "src", "db", "schema.sql"
        )
        with open(schema_path) as f:
            content = f.read()

        # Must have tsvector generated column for embeddingless RAG
        assert "tsvector" in content.lower(), \
            "wiki_entries must have tsvector for full-text search (embeddingless RAG)"
        assert "search_vector" in content or "GENERATED ALWAYS" in content, \
            "wiki_entries must have a generated search_vector column"
        # Must have GIN index for tsvector
        assert "GIN" in content, \
            "wiki_entries must have a GIN index on search_vector"

    def test_wiki_entries_has_required_columns(self):
        """wiki_entries table must have all research-specific columns."""
        import os
        schema_path = os.path.join(
            os.path.dirname(__file__),
            "..", "..", "src", "db", "schema.sql"
        )
        with open(schema_path) as f:
            content = f.read()

        required = [
            "id", "title", "slug", "content", "sources",
            "green_rationale", "red_objections", "consensus_note",
            "tags", "created_at", "updated_at", "verified_at", "invalidated_at"
        ]
        for col in required:
            assert col in content, \
                f"wiki_entries must have column: {col}"

    def test_audit_log_table_exists(self):
        """The audit_log table must record all agent decisions."""
        import os
        schema_path = os.path.join(
            os.path.dirname(__file__),
            "..", "..", "src", "db", "schema.sql"
        )
        with open(schema_path) as f:
            content = f.read()

        assert "CREATE TABLE" in content and "audit_log" in content.lower(), \
            "schema.sql must contain audit_log table"

        required = [
            "id", "cycle_date", "campaign_id", "action_type",
            "target", "green_proposal", "red_objections",
            "coordinator_note", "debate_rounds", "performed_at"
        ]
        for col in required:
            assert col in content, \
                f"audit_log must have column: {col}"

    def test_debate_state_table_exists(self):
        """The debate_state table must track the adversarial debate phases."""
        import os
        schema_path = os.path.join(
            os.path.dirname(__file__),
            "..", "..", "src", "db", "schema.sql"
        )
        with open(schema_path) as f:
            content = f.read()

        assert "CREATE TABLE" in content and "debate_state" in content.lower(), \
            "schema.sql must contain debate_state table"

        # Must track phase, round, proposals, objections, consensus flag
        required = [
            "id", "cycle_date", "campaign_id", "phase",
            "round_number", "green_proposals", "red_objections",
            "consensus_reached"
        ]
        for col in required:
            assert col in content, \
                f"debate_state must have column: {col}"

    def test_webhook_subscriptions_table_exists(self):
        """The webhook_subscriptions table must store endpoint registrations."""
        import os
        schema_path = os.path.join(
            os.path.dirname(__file__),
            "..", "..", "src", "db", "schema.sql"
        )
        with open(schema_path) as f:
            content = f.read()

        assert "CREATE TABLE" in content and "webhook_subscriptions" in content.lower(), \
            "schema.sql must contain webhook_subscriptions table"

        required = ["id", "url", "events", "secret", "active", "created_at"]
        for col in required:
            assert col in content, \
                f"webhook_subscriptions must have column: {col}"

    def test_webhook_delivery_log_table_exists(self):
        """The webhook_delivery_log table must track delivery attempts and retries."""
        import os
        schema_path = os.path.join(
            os.path.dirname(__file__),
            "..", "..", "src", "db", "schema.sql"
        )
        with open(schema_path) as f:
            content = f.read()

        assert "webhook_delivery_log" in content.lower(), \
            "schema.sql must contain webhook_delivery_log table"

        required = [
            "id", "subscription_id", "event", "payload",
            "status", "attempts", "next_retry_at",
            "last_error", "delivered_at"
        ]
        for col in required:
            assert col in content, \
                f"webhook_delivery_log must have column: {col}"

    def test_all_tables_use_uuid_primary_keys(self):
        """All primary tables must use UUID type for id columns."""
        import os
        schema_path = os.path.join(
            os.path.dirname(__file__),
            "..", "..", "src", "db", "schema.sql"
        )
        with open(schema_path) as f:
            content = f.read()

        tables = ["campaigns", "wiki_entries", "audit_log", "debate_state",
                  "webhook_subscriptions", "webhook_delivery_log"]
        for table in tables:
            # Find the full CREATE TABLE block for this table
            # Match from CREATE TABLE to the next semicolon or closing parenthesis at column def level
            pattern = rf"(CREATE TABLE.*?{table}.*?;)"
            match = re.search(pattern, content, re.DOTALL | re.IGNORECASE)
            if match:
                table_def = match.group(1)
                # Primary key id should be UUID
                assert "UUID" in table_def or "gen_random_uuid()" in table_def, \
                    f"{table} should have UUID primary key id (found: {table_def[:100]})"

    def test_wiki_entries_has_unique_slug_constraint(self):
        """wiki_entries.slug must have a UNIQUE constraint to prevent duplicate topics."""
        import os
        schema_path = os.path.join(
            os.path.dirname(__file__),
            "..", "..", "src", "db", "schema.sql"
        )
        with open(schema_path) as f:
            content = f.read()

        assert "UNIQUE" in content and "slug" in content, \
            "wiki_entries.slug must have UNIQUE constraint"
