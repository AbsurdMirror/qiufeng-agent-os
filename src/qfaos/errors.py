class QFAError(Exception):
    """Base exception for all QFAOS SDK errors."""
    pass


class QFAInvalidConfigError(QFAError, ValueError):
    """Raised when the provided configuration is invalid or missing required fields."""
    pass


class QFAUnsupportedChannelError(QFAError, NotImplementedError):
    """Raised when an unsupported channel type is used."""
    pass


class QFAUnsupportedModelError(QFAError, NotImplementedError):
    """Raised when an unsupported model type is used."""
    pass


class QFASecurityDeniedError(QFAError, PermissionError):
    """Raised when a security primitive is denied by policy."""
    pass


class QFASecurityApprovalRequiredError(QFAError):
    """Raised when a security primitive requires approval ticket."""

    def __init__(self, ticket_id: str, message: str):
        super().__init__(message)
        self.ticket_id = ticket_id
