"""Unit tests for evaluation metrics."""

from evals.metrics import grounding_rate, mean_reciprocal_rank, ndcg_at_k, recall_at_k, relevance_at_k


class TestRelevanceAtK:
    def test_all_relevant(self):
        assert relevance_at_k(["a", "b", "c"], {"a", "b", "c"}, k=5) == 1.0

    def test_none_relevant(self):
        assert relevance_at_k(["x", "y"], {"a", "b"}, k=5) == 0.0

    def test_partial(self):
        result = relevance_at_k(["a", "x", "b"], {"a", "b"}, k=3)
        assert abs(result - 2 / 3) < 0.01

    def test_empty_relevant(self):
        assert relevance_at_k(["a", "b"], set(), k=5) == 0.0

    def test_k_zero(self):
        assert relevance_at_k(["a"], {"a"}, k=0) == 0.0


class TestMeanReciprocalRank:
    def test_first_is_relevant(self):
        assert mean_reciprocal_rank(["a", "b", "c"], {"a"}) == 1.0

    def test_second_is_relevant(self):
        assert mean_reciprocal_rank(["x", "a", "b"], {"a"}) == 0.5

    def test_none_relevant(self):
        assert mean_reciprocal_rank(["x", "y"], {"a"}) == 0.0

    def test_empty_relevant(self):
        assert mean_reciprocal_rank(["a"], set()) == 0.0


class TestNdcgAtK:
    def test_perfect_ranking(self):
        scores = {"a": 3, "b": 2, "c": 1}
        assert ndcg_at_k(["a", "b", "c"], scores, k=3) == 1.0

    def test_no_relevant(self):
        assert ndcg_at_k(["x", "y"], {"a": 1}, k=5) == 0.0

    def test_empty_scores(self):
        assert ndcg_at_k(["a"], {}, k=5) == 0.0


class TestGroundingRate:
    def test_fully_grounded(self):
        answer = "Python is a programming language."
        evidence = ["Python is a programming language used for web development."]
        result = grounding_rate(answer, evidence)
        assert result > 0.5

    def test_no_evidence(self):
        assert grounding_rate("Python is great.", []) == 0.0

    def test_empty_answer(self):
        assert grounding_rate("", ["evidence"]) == 0.0


class TestRecallAtK:
    def test_perfect_recall(self):
        assert recall_at_k(["a", "b", "c"], {"a", "b"}, k=5) == 1.0

    def test_partial_recall(self):
        result = recall_at_k(["a"], {"a", "b"}, k=5)
        assert abs(result - 0.5) < 0.01

    def test_no_relevant_found(self):
        assert recall_at_k(["x", "y"], {"a", "b"}, k=5) == 0.0

    def test_empty_relevant(self):
        assert recall_at_k(["a"], set(), k=5) == 0.0
