import json

import pytest

from gnomon.domain.models import MetricScores
from gnomon.judge.ollama import JudgeProtocolError, parse_v1_judge_response
from gnomon.metrics.names import V1_METRICS


def test_valid_response_parses_all_v1_metrics():
    expected = {metric: index / 10 for index, metric in enumerate(V1_METRICS, start=1)}

    result = parse_v1_judge_response(json.dumps(expected))

    assert isinstance(result, MetricScores)
    assert result.scores == expected


def test_out_of_range_values_are_clamped():
    response = {V1_METRICS[0]: 1.5, V1_METRICS[1]: -0.5}

    result = parse_v1_judge_response(json.dumps(response))

    assert result.scores == {V1_METRICS[0]: 1.0, V1_METRICS[1]: 0.0}


def test_malformed_json_is_protocol_error():
    with pytest.raises(JudgeProtocolError):
        parse_v1_judge_response("not JSON")


def test_missing_metric_key_is_protocol_error():
    with pytest.raises(JudgeProtocolError):
        parse_v1_judge_response(json.dumps({V1_METRICS[0]: 0.8}))
