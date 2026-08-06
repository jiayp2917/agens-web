"""Regression coverage for the product application's runtime state."""

from __future__ import annotations

from typing import cast

from web.backend.app import create_app
from web.backend.service import WebGameService


def test_product_app_does_not_expose_removed_evaluation_ledger() -> None:
    app = create_app(service_factory=lambda: cast(WebGameService, object()))

    assert not hasattr(app.state, "evaluation_ledger")
