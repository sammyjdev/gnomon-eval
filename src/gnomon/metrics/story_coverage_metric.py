"""Story coverage metric: prompt builder and score parser (Phase C2).

Evaluates whether a test body adequately exercises the story scenario it
claims to cover. The judge answers 'adequate' (1.0) or 'inadequate' (0.0)
for each (story, test) pair.

Gate: ci_low(story_coverage) >= GATE_THRESHOLD at 95% CI.

Usage pattern mirrors prompts.py but for the binary story-coverage question
rather than the multi-metric V1 JSON format.
"""

from gnomon.metrics.names import STORY_COVERAGE

METRIC_NAME = STORY_COVERAGE
GATE_THRESHOLD = 0.80


def build_prompt(story_description: str, test_body: str) -> str:
    """Build the judge prompt for a single story / test-body pair."""
    return (
        f"Story: {story_description}. Test body:\n{test_body}\n\n"
        "Does this test adequately exercise the story scenario? "
        "Answer 'adequate' (score 1.0) or 'inadequate' (score 0.0)."
    )


def parse_score(judge_response: str) -> float:
    """Extract a score from the judge's text response.

    Returns 1.0 if the response signals adequacy, 0.0 otherwise.
    'inadequate' takes priority over 'adequate' so partial matches don't
    flip the sign (e.g. '...not adequate...' still reads as inadequate).
    """
    text = judge_response.lower().strip()
    if "inadequate" in text:
        return 0.0
    if "adequate" in text:
        return 1.0
    return 0.0
