"""Connector framework exception hierarchy.

All connector-specific exceptions inherit from ConnectorError so callers
can catch the entire family with a single except clause.
"""


class ConnectorError(Exception):
    """Base for all connector framework errors."""


class ConnectorAuthError(ConnectorError):
    """Authentication against an external system failed."""


class ConnectorValidationError(ConnectorError):
    """Connector configuration or credentials did not pass validation."""


class ConnectorTimeoutError(ConnectorError):
    """Remote call to an external system exceeded the timeout budget."""


class ConnectorIngestionError(ConnectorError):
    """Telemetry collection or normalization failed."""


class ConnectorNotFoundError(ConnectorError):
    """A requested connector ID does not exist in the registry."""


class DuplicateConnectorError(ConnectorError):
    """Attempt to register a connector that is already registered."""
