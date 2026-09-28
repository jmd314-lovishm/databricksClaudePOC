"""
Centralized test configuration for MCP server integration tests.

Each test module uses a unique schema to enable parallel test execution without conflicts.
"""

import os

# =============================================================================
# Core Test Configuration
# =============================================================================

# Default catalog for all tests (can be overridden via env var)
TEST_CATALOG = os.environ.get("TEST_CATALOG", "ai_dev_kit_test")

# =============================================================================
# Per-Module Schema Configuration
# Each module gets its own schema to avoid conflicts during parallel execution
# =============================================================================

SCHEMAS = {
    # SQL and core tests
    "sql": "test_sql",
    "warehouse": "test_warehouse",

    # Unity catalog tests
    "unity_catalog": "test_uc",
}

# =============================================================================
# Resource Naming Conventions
# =============================================================================

# Prefix for all test resources (pipelines, endpoints, etc.)
TEST_RESOURCE_PREFIX = "ai_dev_kit_test_"

# =============================================================================
# Helper Functions
# =============================================================================

def get_full_schema_name(module: str) -> str:
    """Get fully-qualified schema name for a test module."""
    return f"{TEST_CATALOG}.{SCHEMAS[module]}"

def get_table_name(module: str, table: str) -> str:
    """Get fully-qualified table name for a test module."""
    return f"{TEST_CATALOG}.{SCHEMAS[module]}.{table}"
