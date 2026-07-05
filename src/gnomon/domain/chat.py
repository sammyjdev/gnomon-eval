"""Domain models for ChatEval: multi-turn, tool-calling conversation cases.

Unlike EvalCase/RagResponse (question+contexts, one RAG turn), a ChatCase is
a full conversation up to and including the customer's latest message, and a
ChatResult reports which tool (if any) the target called plus its final
reply -- the two things DeepEval's ToolCorrectnessMetric and GEval need to
score. There is no expected_answer: correctness here is either "called the
right tool" (a deterministic diff, not a judge call) or a GEval criterion
applied to reply_text.
"""

from pydantic import BaseModel, ConfigDict, Field


class ChatCase(BaseModel):
    """One ChatEval case: a conversation, the tenant it runs against, and
    what a correct response looks like."""

    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    conversation: list[dict] = Field(min_length=1)
    tenant: dict
    expected_tools: list[str] = Field(default_factory=list)
    criteria: str | None = None


class ChatResult(BaseModel):
    """A target's response to a ChatCase: which tool fired (if any), its
    arguments, the final customer-facing reply, and cost/latency."""

    model_config = ConfigDict(frozen=True)

    tool_called: str | None = None
    tool_args: dict = Field(default_factory=dict)
    reply_text: str
    total_tokens: int = Field(ge=0)
    latency_ms: float = Field(ge=0.0)
