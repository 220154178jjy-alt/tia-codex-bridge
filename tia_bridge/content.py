import re
import xml.etree.ElementTree as ET

from .errors import BridgeError

BLOCK_TAGS = {"SW.Blocks.OB", "SW.Blocks.FC", "SW.Blocks.FB", "SW.Blocks.GlobalDB", "SW.Blocks.InstanceDB"}


def validate_source(data: bytes, suffix: str) -> None:
    if not data:
        raise BridgeError("INVALID_SOURCE", "Source file is empty.")
    if suffix == ".scl":
        try:
            text = data.decode("ascii")
        except UnicodeError:
            raise BridgeError("INVALID_SOURCE", "This initial Openness SCL route accepts ASCII source only.") from None
        if "\x00" in text:
            raise BridgeError("INVALID_SOURCE", "SCL contains a NUL byte.")
        return  # TIA, not a regex, validates SCL semantics.
    if suffix != ".xml":
        raise BridgeError("UNSUPPORTED_FILE", "Only SCL and SimaticML block XML imports are supported.")
    try:
        text = data.decode("utf-8-sig")
        if re.search(r"<!\s*(DOCTYPE|ENTITY)", text, re.I):
            raise ValueError("DTD")
        root = ET.fromstring(text)
        if root.tag != "Document" or not any(child.tag in BLOCK_TAGS for child in root):
            raise ValueError("not block document")
        if any(child.tag not in BLOCK_TAGS | {"Engineering", "DocumentInfo"} for child in root):
            raise ValueError("unexpected engineering object")
    except (ValueError, UnicodeError, ET.ParseError):
        raise BridgeError("INVALID_SOURCE", "Expected UTF-8 SimaticML block XML without DTD/entity declarations.") from None


def redact_diagnostic(value: str) -> str:
    """Best-effort minimization of compiler messages, not a data-loss-prevention boundary."""
    text = str(value)[:8192]
    text = re.sub(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", "[address]", text)
    text = re.sub(r"(?i)(?:https?|ssh|ftp)://[^\s<>\"']+", "[url]", text)
    text = re.sub(r"[A-Za-z]:[\\/][^\r\n\"<>]+", "[local-path]", text)
    text = re.sub(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", "[email]", text)
    text = re.sub(r"(?i)\b(password|api[_-]?key|access[_-]?token|secret)\b\s*[:=]\s*[^\s;,]+",
                  r"\1=[redacted]", text)
    text = re.sub(r"\b(?:sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,})",
                  "[credential]", text)
    return text
