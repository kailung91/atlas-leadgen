"""
Спеціалізовані винятки для скрапера
"""
from typing import Optional


class ScraperException(Exception):
    """Базовий клас для всіх винятків скрапера."""
    pass


class HttpException(ScraperException):
    """Помилки HTTP запитів."""
    def __init__(self, message: str, status_code: Optional[int] = None, url: Optional[str] = None):
        self.status_code = status_code
        self.url = url
        super().__init__(f"{message} (Статус код: {status_code}, URL: {url})")


class TooManyRequestsException(HttpException):
    """Забагато запитів, потрібно зробити паузу."""
    pass


class PageNotFoundException(HttpException):
    """Сторінка не знайдена (404)."""
    pass


class BlockedException(HttpException):
    """Скрапер заблокований сайтом."""
    pass


class KvedSkipException(ScraperException):
    """Сигнал для пропуску поточного КВЕДу та переходу до наступного."""
    def __init__(self, kved: str, reason: str):
        self.kved = kved
        self.reason = reason
        super().__init__(f"Пропуск КВЕДу {kved}: {reason}")


class MaxRetriesExceededException(ScraperException):
    """Перевищено максимальну кількість спроб."""
    pass


class ScraperMaxFailuresException(ScraperException):
    """Перевищено максимальну кількість послідовних невдач."""
    pass


class LockException(ScraperException):
    """Помилки, пов'язані з блокуванням."""
    pass


class DatabaseException(ScraperException):
    """Помилки роботи з базою даних."""
    def __init__(self, message: str, original_exception: Optional[Exception] = None):
        self.original_exception = original_exception
        if original_exception:
            message = f"{message}: {str(original_exception)}"
        super().__init__(message)


class ParseException(ScraperException):
    """Помилки парсингу HTML."""
    pass 