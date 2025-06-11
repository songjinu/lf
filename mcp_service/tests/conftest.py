import pytest
import asyncio

# @pytest.fixture(scope="session")
# def event_loop_policy():
#     # For some environments, explicitly setting asyncio event loop policy can be helpful
#     # return asyncio.DefaultEventLoopPolicy() # Or other policies if needed
#     # However, pytest-asyncio usually handles this well.
#     pass

# If you were using FastAPI's TestClient, you might define a client fixture here:
# from fastapi.testclient import TestClient
# from mcp_service.server import app
#
# @pytest.fixture(scope="module")
# def test_client():
#     client = TestClient(app)
#     yield client
