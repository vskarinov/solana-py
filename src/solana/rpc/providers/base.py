"""Base RPC Provider."""

from typing import Any, Optional

from ..types import RPCMethod, RPCResponse


class BaseProvider:
    """Base class for RPC providers to implement."""

    def make_request(self, method: RPCMethod, *params: Any, header_opt: Optional[dict] = None) -> RPCResponse:
        """Make a request ot the rpc endpoint."""
        raise NotImplementedError("Providers must implement this method")

    def is_connected(self) -> bool:
        """Health check."""
        raise NotImplementedError("Providers must implement this method")
