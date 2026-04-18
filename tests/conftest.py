"""Shared test configuration and fixtures."""

import os

# Ensure API key is available for app startup validation during tests.
# Tests use mocks so no real API calls are made.
os.environ.setdefault("OPENROUTER_API_KEY", "sk-test-for-pytest")
