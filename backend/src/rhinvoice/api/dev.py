"""Application factory for ``uvicorn --factory --reload`` during development."""

from fastapi import FastAPI

from rhinvoice.api.app import create_app
from rhinvoice.api.container import build_container
from rhinvoice.api.settings import Settings


def app() -> FastAPI:
    return create_app(build_container(Settings()))
