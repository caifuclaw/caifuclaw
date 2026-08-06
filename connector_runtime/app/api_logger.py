import logging


logger = logging.getLogger("connector_runtime.api")


def log_api_call(**payload) -> None:
    """Connector-compatible API logger.

    The business app owns persistent API request logs. The runtime keeps a
    lightweight log here so adapters do not depend on customer databases.
    """
    logger.info("platform_api_call", extra={"platform_api_call": payload})
