"""Unit tests for core modules (graph, vectorstore, llm, embeddings)."""

from unittest.mock import MagicMock, patch

from app.core.embeddings import get_embeddings
from app.core.graph import check_nebula_health, get_nebula_session, reset_pool
from app.core.llm import get_llm


class TestGetLLM:
    def test_returns_llm_with_correct_model(self):
        llm = get_llm(temperature=0.5)
        assert llm.temperature == 0.5

    def test_default_temperature(self):
        llm = get_llm()
        assert llm.temperature == 0.0


class TestGetEmbeddings:
    def test_returns_embeddings_instance(self):
        emb = get_embeddings()
        assert emb is not None


class TestGetNebulaSession:
    @patch("app.core.graph._get_pool")
    def test_session_context_manager(self, mock_get_pool):
        mock_pool = MagicMock()
        mock_session = MagicMock()
        mock_pool.get_session.return_value = mock_session
        mock_get_pool.return_value = mock_pool

        with get_nebula_session() as session:
            assert session == mock_session

        mock_session.release.assert_called_once()

    @patch("app.core.graph._get_pool")
    def test_session_released_on_exception(self, mock_get_pool):
        mock_pool = MagicMock()
        mock_session = MagicMock()
        mock_pool.get_session.return_value = mock_session
        mock_get_pool.return_value = mock_pool

        try:
            with get_nebula_session():
                raise ValueError("test error")
        except ValueError:
            pass

        mock_session.release.assert_called_once()


class TestCheckNebulaHealth:
    @patch("app.core.graph.get_nebula_session")
    async def test_healthy(self, mock_session_ctx):
        mock_session = MagicMock()
        mock_result = MagicMock()
        mock_result.is_succeeded.return_value = True
        mock_session.execute.return_value = mock_result
        mock_session_ctx.return_value.__enter__ = MagicMock(return_value=mock_session)
        mock_session_ctx.return_value.__exit__ = MagicMock(return_value=False)

        result = await check_nebula_health()
        assert result is True

    @patch("app.core.graph.get_nebula_session")
    async def test_unhealthy(self, mock_session_ctx):
        mock_session_ctx.return_value.__enter__ = MagicMock(side_effect=ConnectionError("fail"))
        mock_session_ctx.return_value.__exit__ = MagicMock(return_value=False)

        result = await check_nebula_health()
        assert result is False


class TestResetPool:
    @patch("app.core.graph._close_pool")
    def test_resets_pool(self, mock_close):
        import app.core.graph as graph_module

        graph_module._pool = MagicMock()
        reset_pool()
        mock_close.assert_called_once()
