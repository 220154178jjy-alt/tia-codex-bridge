class BridgeError(Exception):
    """An intentionally public, credential-free error."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def public_error(exc: Exception) -> dict:
    if isinstance(exc, BridgeError):
        return {"code": exc.code, "message": str(exc)}
    # Siemens/OS exceptions can embed project paths, usernames and credentials.
    return {"code": "OPERATION_FAILED", "message":
            "Operation failed. Inspect the local TIA UI; raw exception details are not forwarded."}
