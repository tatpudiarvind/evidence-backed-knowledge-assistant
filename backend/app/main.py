"""The server's entry point: `uvicorn app.main:app`.

Importing this module sets up logging for the whole process, so only servers import it. Tests
build their apps with `app.factory.create_app` instead.
"""

from app.core.config import get_settings
from app.core.logs import configure_logging
from app.factory import create_app

settings = get_settings()
configure_logging(settings)
app = create_app(settings)
