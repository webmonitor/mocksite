"""Fixtures for integration tests."""

from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest_asyncio

from tests.integration.harness import Stack, running_stack


@pytest_asyncio.fixture
async def stack() -> AsyncGenerator[Stack]:
    async with running_stack() as running:
        yield running
