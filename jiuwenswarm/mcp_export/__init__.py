"""Exported MCP surfaces: native capabilities served to external MCP clients.

Nothing in here changes how jiuwenswarm's own agents get their tools -- those stay
natively assembled inside the harness, where the closed sets and permission floors
live. This package is the outward door: the same toolkit code, wrapped as a stdio
MCP server, with every rail executing on this side of the boundary.
"""
