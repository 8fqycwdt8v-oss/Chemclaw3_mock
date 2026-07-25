"""mock-vendor: an HTTP-transport FastMCP server for building-block search & pricing.

A thin transport wrapper (same pattern as Chemclaw3's own `mcp_servers/molfp/server.py`) — all
logic lives in `vendor.py`. Unlike mcp-molfp/mcp-rxnfp (stdio, spawned as a subprocess), this one
runs standalone over Streamable HTTP so it exercises the `HttpMcpServerSpec` path in
`CHEMCLAW_MCP_SERVERS`:

    CHEMCLAW_MCP_SERVERS='[{"transport":"http","name":"mock-vendor",
        "url":"http://localhost:8091/mcp","allowed_tools":["search_building_blocks","get_price"]}]'

Run with `python -m app.mcp_tools.vendor_server` (host/port from `MOCK_MCP_VENDOR_HOST` /
`MOCK_MCP_VENDOR_PORT`, default 0.0.0.0:8091).
"""

from mcp.server.fastmcp import FastMCP

from app.config import settings
from app.mcp_tools.vendor import price, search

server = FastMCP("mock-vendor", host=settings.mcp_vendor_host, port=settings.mcp_vendor_port)


@server.tool()
def search_building_blocks(query: str) -> list[dict]:
    """Search the mock vendor catalog by name or SMILES substring; returns matching listings."""
    return [
        {
            "catalog_id": b.catalog_id,
            "name": b.name,
            "smiles": b.smiles,
            "vendor": b.vendor,
            "price_usd": b.price_usd,
            "pack_size": b.pack_size,
            "lead_time_days": b.lead_time_days,
            "in_stock": b.in_stock,
        }
        for b in search(query)
    ]


@server.tool()
def get_price(catalog_id: str) -> dict:
    """Return full pricing/availability detail for one catalog id, or an error if unknown."""
    block = price(catalog_id)
    if block is None:
        return {"error": f"unknown catalog_id {catalog_id!r}"}
    return {
        "catalog_id": block.catalog_id,
        "name": block.name,
        "smiles": block.smiles,
        "vendor": block.vendor,
        "price_usd": block.price_usd,
        "pack_size": block.pack_size,
        "lead_time_days": block.lead_time_days,
        "in_stock": block.in_stock,
    }


def main() -> None:
    server.run(transport="streamable-http")


if __name__ == "__main__":
    main()
