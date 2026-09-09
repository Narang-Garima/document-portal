"""Paid RAG quality suite.

Run with:
    $env:RUN_RAG_EVALS="1"
    python -m pytest evals/test_rag_deepeval.py -v

The suite is intentionally opt-in because judge-model calls consume API credits.
"""

import os

import pytest

pytest.importorskip("deepeval")
from deepeval import assert_test
from deepeval.metrics import AnswerRelevancyMetric, ContextualRelevancyMetric, FaithfulnessMetric
from deepeval.test_case import LLMTestCase

from src.document_chat.retrieval import answer_question

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_RAG_EVALS") != "1",
    reason="Set RUN_RAG_EVALS=1 to run paid integration evaluations.",
)

TEST_CASES = [
    ("What is the main subject of the indexed document?", "main-topic retrieval"),
    ("Summarize the most important facts in the indexed document.", "summary grounding"),
    ("Which technologies are mentioned?", "entity and technology extraction"),
    ("What architecture or workflow is described?", "architecture retrieval"),
    ("How is the system deployed?", "deployment fact retrieval"),
    ("What evaluation tools or metrics are reported?", "metric retrieval"),
    ("What are the key entities in the document?", "entity completeness"),
    ("What limitations or future improvements are described?", "limitations grounding"),
    ("Which facts are unique or especially important?", "cross-chunk synthesis"),
    ("What information is not available in the document?", "hallucination resistance"),
]


@pytest.mark.parametrize(("question", "focus"), TEST_CASES, ids=[focus for _, focus in TEST_CASES])
def test_rag_quality(question: str, focus: str):
    del focus
    result = answer_question(question)
    context = [source["content"] for source in result["sources"]]
    case = LLMTestCase(
        input=question,
        actual_output=result["answer"],
        retrieval_context=context,
    )
    assert_test(
        case,
        [
            AnswerRelevancyMetric(threshold=0.60),
            FaithfulnessMetric(threshold=0.70),
            ContextualRelevancyMetric(threshold=0.60),
        ],
    )
