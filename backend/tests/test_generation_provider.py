import pytest

from app.generation.errors import GenerationFailure
from app.generation.provider import FakeAnswerGenerator
from app.generation.types import Claim, GeneratedAnswer, GenerationContext


def _context() -> GenerationContext:
    return GenerationContext(evidence=[], commitments=[])


def test_fake_generator_default_response_is_insufficient_evidence():
    generator = FakeAnswerGenerator()
    result = generator.generate("q", _context())
    assert result.status == "insufficient_evidence"
    assert result.claims == []


def test_fake_generator_returns_fixed_answer():
    fixed = GeneratedAnswer(status="answered", claims=[Claim(text="x", citation_ids=["E1"], claim_type="evidence")])
    generator = FakeAnswerGenerator(respond_with=fixed)
    assert generator.generate("q", _context()) is fixed


def test_fake_generator_returns_callable_answer_inspecting_context():
    context = GenerationContext(evidence=[], commitments=[])

    def responder(query: str, ctx: GenerationContext) -> GeneratedAnswer:
        assert query == "q"
        assert ctx is context
        return GeneratedAnswer(status="answered", claims=[])

    generator = FakeAnswerGenerator(respond_with=responder)
    result = generator.generate("q", context)
    assert result.status == "answered"


def test_fake_generator_can_simulate_provider_failure():
    generator = FakeAnswerGenerator(raise_failure=True)
    with pytest.raises(GenerationFailure):
        generator.generate("q", _context())


def test_fake_generator_records_last_call():
    context = _context()
    generator = FakeAnswerGenerator()
    generator.generate("my query", context)
    assert generator.last_query == "my query"
    assert generator.last_context is context
