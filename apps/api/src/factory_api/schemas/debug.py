"""Test-only response bodies.

Everything in this module backs an endpoint that only ever exists in ``development`` or
``test`` — see ``factory_api.routers.debug``.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class VerificationCodeDebugResponse(BaseModel):
    """The most recent one-time code sent to an address, for e2e tests to read.

    Never present outside development/test: production and staging never register this
    router, and the console transport it depends on refuses to run in production anyway.
    """

    model_config = ConfigDict(extra="forbid")

    email: str
    code: str
