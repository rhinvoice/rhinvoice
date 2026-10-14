"""Rhinvoice without Docker: one program that starts its own database (ADR 0021).

The top layer: it starts the bundled PostgreSQL, finds a browser for the PDFs and runs
the same web server as the Docker setup. Nothing below it knows that it exists.
"""
