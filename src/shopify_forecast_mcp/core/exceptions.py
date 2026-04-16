"""Custom exception classes for Shopify API errors.

These exceptions provide structured error information from Shopify's
GraphQL API, enabling callers to handle throttling, query errors,
and bulk operation failures distinctly.
"""

from __future__ import annotations


class ShopifyGraphQLError(Exception):
    """Raised when the Shopify GraphQL API returns non-throttle errors.

    Stores the raw ``errors`` list from the GraphQL response so callers
    can inspect individual error messages and extensions.
    """

    def __init__(self, errors: list[dict]) -> None:
        self.errors = errors
        super().__init__(str(self))

    def __str__(self) -> str:
        messages = [e.get("message", str(e)) for e in self.errors]
        return "; ".join(messages)


class ShopifyThrottledError(ShopifyGraphQLError):
    """Raised when max retries are exceeded on THROTTLED responses.

    Shopify returns HTTP 200 with ``errors[].extensions.code == "THROTTLED"``
    when the cost bucket is exhausted.  The client retries with calculated
    backoff, but after ``MAX_RETRIES`` this exception is raised.
    """

    pass


class BulkOperationError(Exception):
    """Raised when a Shopify bulk operation ends in a non-success state.

    Attributes:
        operation_id: The GID of the failed bulk operation.
        status: Terminal status (FAILED, CANCELED, EXPIRED).
        error_code: Shopify error code, if any.
    """

    def __init__(
        self,
        operation_id: str,
        status: str,
        error_code: str | None = None,
    ) -> None:
        self.operation_id = operation_id
        self.status = status
        self.error_code = error_code
        super().__init__(
            f"Bulk operation {operation_id} ended with status: {status}"
            + (f", error: {error_code}" if error_code else "")
        )


class ShopifyCliError(Exception):
    """Raised when the Shopify CLI subprocess returns a non-zero exit code
    or produces unparseable output."""

    pass


class ShopifyCliNotFoundError(ShopifyCliError):
    """Raised when neither an access token nor the Shopify CLI is available.

    Provides a user-friendly message with setup instructions for both
    the CLI (interactive) and token (headless) paths.
    """

    pass
