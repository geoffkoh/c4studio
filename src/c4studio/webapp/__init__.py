"""FastAPI backend for the c4studio React web application.

This package exposes a small JSON API that lets a single-page frontend
browse Structurizr sources on disk, load a workspace, enumerate its views
and fetch React Flow-shaped graph data for the supported view types
(``systemContext``, ``container`` and ``component``).

This is the sole UI backend for c4studio; it serves the built React
single-page app and its JSON API.
"""

from __future__ import annotations
