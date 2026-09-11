"""Deterministic known-fail perturbation probes (JA-04, ADR-0012)."""

import itertools
import re
from typing import Literal

from gnomon.domain.models import EvalCase

KnownFailKind = Literal["number_swap", "identifier_swap", "unsupported_claim"]

UNSUPPORTED_CLAIM_SENTENCE: str = (
    "Além disso, uma apuração interna nunca incluída nos contextos "
    "registrou índice de consistência de 0,98 em todos os pilotos."
)

FABRICATED_IDENTIFIER_ROOT: str = "zzqqxx_inexistente"


def known_fail_perturbations(case: EvalCase) -> list[tuple[KnownFailKind, str]]:
    """Zero or more (kind, answer) pairs, each unsupported by
    case.expected_contexts by construction. Deterministic (NFR-03).
    """
    ans_orig = case.expected_answer
    contexts = case.expected_contexts
    maxlen = max([len(c) for c in contexts] + [1])

    pairs: list[tuple[KnownFailKind, str]] = []

    # 1. number_swap
    m_num = re.search(r"\d+", ans_orig)
    if m_num is not None:
        run = m_num.group(0)
        cand_found = None
        for length in range(len(run), max(len(run), maxlen) + 2):
            for digit in "9876543210":
                cand = digit * length
                if cand != run and all(cand not in c for c in contexts):
                    cand_found = cand
                    break
            if cand_found is not None:
                break
        if cand_found is not None:
            ans = ans_orig[: m_num.start()] + cand_found + ans_orig[m_num.end() :]
            pairs.append(("number_swap", ans))

    # 2. identifier_swap
    m_ident = re.search(r"`([^`]+)`", ans_orig)
    if m_ident is not None:
        orig_ident = m_ident.group(1)
        ident_found = None
        for i in itertools.count(1):
            cand_ident = f"{FABRICATED_IDENTIFIER_ROOT}_{i}"
            if cand_ident != orig_ident and all(cand_ident not in c for c in contexts):
                ident_found = cand_ident
                break
        if ident_found is not None:
            ans = ans_orig[: m_ident.start() + 1] + ident_found + ans_orig[m_ident.end() - 1 :]
            pairs.append(("identifier_swap", ans))

    # 3. unsupported_claim
    if not any(UNSUPPORTED_CLAIM_SENTENCE in c for c in contexts):
        sep = " " if ans_orig.endswith((".", "!", "?", "…")) else ". "
        ans = ans_orig + sep + UNSUPPORTED_CLAIM_SENTENCE
        pairs.append(("unsupported_claim", ans))

    return pairs
