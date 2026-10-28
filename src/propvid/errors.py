"""Custom exceptions for propvid."""


class PropvidError(Exception):
    """Base exception for all propvid errors."""
    exit_code: int = 4

    def __init__(self, message: str, exit_code: int = 4) -> None:
        super().__init__(message)
        self.message = message
        self.exit_code = exit_code


class InputError(PropvidError):
    """Raised when input data, schema, or media fails validation (exit code 2)."""
    def __init__(self, message: str) -> None:
        super().__init__(message, exit_code=2)


class RenderError(PropvidError):
    """Raised when video rendering or FFmpeg encoding fails (exit code 3)."""
    def __init__(self, message: str) -> None:
        super().__init__(message, exit_code=3)


class AudioError(PropvidError):
    """Raised on non-fatal audio/TTS synthesis issues.

    Audio errors are caught internally and degrade to silent or synth-only mode
    with a warning rather than aborting the pipeline.
    """
    def __init__(self, message: str) -> None:
        super().__init__(message, exit_code=4)


class LLMError(PropvidError):
    """Raised when LLM completion, network, or parsing fails critically."""
    def __init__(self, message: str) -> None:
        super().__init__(message, exit_code=4)
