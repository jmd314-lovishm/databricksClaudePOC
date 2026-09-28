"""
Pytest fixtures for databricks-mcp-server integration tests.

Uses centralized configuration from test_config.py.
Each test module gets its own schema to enable parallel execution.
"""

import logging
import os
from pathlib import Path
from typing import Generator

import pytest
from databricks.sdk import WorkspaceClient

from .test_config import TEST_CATALOG, SCHEMAS, TEST_RESOURCE_PREFIX, get_full_schema_name

# Load .env.test file if it exists
_env_file = Path(__file__).parent.parent / ".env.test"
if _env_file.exists():
    from dotenv import load_dotenv
    load_dotenv(_env_file)
    logging.getLogger(__name__).info(f"Loaded environment from {_env_file}")

logger = logging.getLogger(__name__)


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line("markers", "integration: mark test as integration test requiring Databricks")
    config.addinivalue_line("markers", "slow: mark test as slow (may take a while to run)")


# =============================================================================
# Core Fixtures (Session-scoped)
# =============================================================================

@pytest.fixture(scope="session")
def workspace_client() -> WorkspaceClient:
    """
    Create a WorkspaceClient for the test session.

    Uses standard Databricks authentication:
    1. DATABRICKS_HOST + DATABRICKS_TOKEN env vars
    2. ~/.databrickscfg profile
    """
    try:
        client = WorkspaceClient()
        # Verify connection works
        client.current_user.me()
        logger.info(f"Connected to Databricks: {client.config.host}")
        return client
    except Exception as e:
        pytest.skip(f"Could not connect to Databricks: {e}")


@pytest.fixture(scope="session")
def current_user(workspace_client: WorkspaceClient) -> str:
    """Get current user's email/username."""
    return workspace_client.current_user.me().user_name


@pytest.fixture(scope="session")
def test_catalog(workspace_client: WorkspaceClient, warehouse_id: str) -> str:
    """
    Ensure test catalog exists and current user has permissions.

    Returns the catalog name.
    """
    try:
        workspace_client.catalogs.get(TEST_CATALOG)
        logger.info(f"Using existing catalog: {TEST_CATALOG}")
    except Exception:
        logger.info(f"Creating catalog: {TEST_CATALOG}")
        workspace_client.catalogs.create(name=TEST_CATALOG)

    # Grant ALL_PRIVILEGES on the catalog to the current user using SQL
    current_user = workspace_client.current_user.me().user_name
    try:
        # Use backticks to escape the email address (contains @)
        grant_sql = f"GRANT ALL PRIVILEGES ON CATALOG `{TEST_CATALOG}` TO `{current_user}`"
        workspace_client.statement_execution.execute_statement(
            warehouse_id=warehouse_id,
            statement=grant_sql,
            wait_timeout="30s",
        )
        logger.info(f"Granted ALL_PRIVILEGES on {TEST_CATALOG} to {current_user}")
    except Exception as e:
        logger.warning(f"Could not grant permissions on catalog (may already have them): {e}")

    return TEST_CATALOG


@pytest.fixture(scope="session")
def warehouse_id(workspace_client: WorkspaceClient) -> str:
    """
    Get a running SQL warehouse for tests.

    Prefers shared endpoints, falls back to any running warehouse.
    """
    from databricks.sdk.service.sql import State

    warehouses = list(workspace_client.warehouses.list())

    # Priority: running shared endpoint
    for w in warehouses:
        if w.state == State.RUNNING and "shared" in (w.name or "").lower():
            logger.info(f"Using warehouse: {w.name} ({w.id})")
            return w.id

    # Fallback: any running warehouse
    for w in warehouses:
        if w.state == State.RUNNING:
            logger.info(f"Using warehouse: {w.name} ({w.id})")
            return w.id

    # No running warehouse found
    pytest.skip("No running SQL warehouse available for tests")


# =============================================================================
# Schema Fixtures (Module-scoped, per test module)
# =============================================================================

def _create_test_schema(
    workspace_client: WorkspaceClient,
    test_catalog: str,
    schema_name: str,
) -> Generator[str, None, None]:
    """Helper to create and cleanup a test schema."""
    full_schema_name = f"{test_catalog}.{schema_name}"

    # Drop schema if exists (cascade to remove all objects)
    try:
        logger.info(f"Dropping existing schema: {full_schema_name}")
        workspace_client.schemas.delete(full_schema_name, force=True)
    except Exception as e:
        logger.debug(f"Schema delete failed (may not exist): {e}")

    # Create fresh schema
    logger.info(f"Creating schema: {full_schema_name}")
    try:
        workspace_client.schemas.create(
            name=schema_name,
            catalog_name=test_catalog,
        )
    except Exception as e:
        if "already exists" in str(e).lower():
            logger.info(f"Schema already exists, reusing: {full_schema_name}")
        else:
            raise

    yield schema_name

    # Cleanup after tests
    try:
        logger.info(f"Cleaning up schema: {full_schema_name}")
        workspace_client.schemas.delete(full_schema_name, force=True)
    except Exception as e:
        logger.warning(f"Failed to cleanup schema: {e}")


@pytest.fixture(scope="module")
def sql_schema(workspace_client: WorkspaceClient, test_catalog: str) -> Generator[str, None, None]:
    """Schema for SQL tests."""
    yield from _create_test_schema(workspace_client, test_catalog, SCHEMAS["sql"])

