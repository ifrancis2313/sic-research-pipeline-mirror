"""The Factor Registry itself: adopted factor definitions held as data, not code."""

from __future__ import annotations

from qepm.contracts import FactorChangeProposal, FactorDefinition
from qepm.factor_governance import validate_factor_change


class FactorRegistry:
    """Currently-adopted factor definitions, keyed by name.

    A Lead Analyst pitch lands here via register()/amend() - never as a
    code change to the Exposure Optimizer or any other downstream module.
    """

    def __init__(self) -> None:
        self._factors: dict[str, FactorDefinition] = {}

    def register(self, factor: FactorDefinition) -> None:
        _validate_factor_definition(factor)
        if factor.name in self._factors:
            raise ValueError(
                f"factor {factor.name!r} is already registered; use amend() with an approved change proposal"
            )
        self._factors[factor.name] = factor

    def amend(self, name: str, proposal: FactorChangeProposal) -> None:
        """Apply the exact, evidence-approved replacement definition.

        The proposal carries the replacement rather than accepting free-form
        keyword changes.  This prevents an approval for one methodology from
        being used to install a different one.
        """
        if name not in self._factors:
            raise KeyError(f"no factor named {name!r} registered")
        if proposal.factor_name != name:
            raise ValueError(
                f"factor-change proposal for {proposal.factor_name!r} does not match amendment target {name!r}"
            )
        validate_factor_change(proposal)
        replacement = proposal.proposed_definition
        if replacement is None:
            raise ValueError("factor-change proposal must include its exact proposed definition")
        if replacement.name != name:
            raise ValueError(
                f"proposed definition for {replacement.name!r} does not match amendment target {name!r}"
            )
        if replacement == self._factors[name]:
            raise ValueError("factor-change proposal does not change the adopted definition")
        _validate_factor_definition(replacement)
        self._factors[name] = replacement

    def get(self, name: str) -> FactorDefinition:
        return self._factors[name]

    @property
    def factors(self) -> dict[str, FactorDefinition]:
        return dict(self._factors)


def _validate_factor_definition(factor: FactorDefinition) -> None:
    """Keep registry weights economically meaningful and numerically safe."""
    from math import isfinite

    if not isfinite(factor.weight) or factor.weight < 0:
        raise ValueError(f"factor {factor.name!r} weight must be finite and non-negative")
