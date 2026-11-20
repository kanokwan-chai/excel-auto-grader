"""Custom exceptions for the Excel Grading Engine."""


class ExcelEngineError(Exception):
    """Base exception for Excel grading engine errors."""

    def __init__(self, message: str, code: str = "EXCEL_ENGINE_ERROR"):
        super().__init__(message)
        self.message = message
        self.code = code


class FileSecurityError(ExcelEngineError):
    """Raised when a file fails security checks (zip bomb, invalid format, oversized)."""

    def __init__(self, message: str, code: str = "FILE_SECURITY_ERROR"):
        super().__init__(message, code=code)


class CorruptedExcelError(ExcelEngineError):
    """Raised when an Excel file cannot be opened or is corrupted."""

    def __init__(self, message: str, code: str = "CORRUPTED_EXCEL_FILE"):
        super().__init__(message, code=code)


class RecalculationError(ExcelEngineError):
    """Raised when LibreOffice headless recalculation fails or times out."""

    def __init__(self, message: str, code: str = "RECALCULATION_ERROR"):
        super().__init__(message, code=code)
