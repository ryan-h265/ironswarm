from typing import Any, Protocol


class NodeType(Protocol):
    """Protocol defining the interface for distributed nodes in IronSwarm."""

    identity: str
    state: dict[str, Any]
    running: bool
    scheduler: Any
    transport: Any
    bootstrap_nodes: list[str]

    @property
    def count(self) -> int:
        """Total number of nodes in the cluster."""
        ...

    @property
    def index(self) -> int | None:
        """Zero-based index of this node in the sorted list, or None if not registered."""
        ...

    async def bind(self) -> None:
        """Bind transport and register with bootstrap nodes."""
        ...

    async def run(self) -> None:
        """Run main node event loop."""
        ...

    async def update_loop(self) -> None:
        """Periodic update loop for neighbor gossip."""
        ...

    async def stats(self) -> None:
        """Periodic stats output loop."""
        ...

    def pick_random_neighbours(
        self, id: str, node_list: list[tuple[str, dict[str, Any]]], n: int = 5, exclude_self: bool = True
    ) -> list[tuple[str, dict[str, Any]]]:
        """Pick random neighbors from node list."""
        ...

    async def update_neighbours(self, shutting_down: bool = False) -> None:
        """Gossip state updates to random neighbors."""
        ...

    def show(self) -> None:
        """Display current CRDT state (debug method)."""
        ...

    async def shutdown(self) -> None:
        """Graceful shutdown sequence."""
        ...
