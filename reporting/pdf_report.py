"""
Public reporting entrypoint.

The project previously held multiple PDF implementations in this module.
To avoid import ambiguity, this file now re-exports the canonical generator.
"""

from __future__ import annotations

from reporting.pdf_report_v2 import create_report_pdf

__all__ = ["create_report_pdf"]
