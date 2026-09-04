"""
Модуль для налаштування системи логування.
"""
import logging
import os
import sys
from datetime import datetime
from typing import Optional, Dict, Any, List

from config import LOGGING_CONFIG


class ColoredFormatter(logging.Formatter):
    """Форматувальник з підтримкою кольорів для консольного виводу."""
    
    # Кольори ANSI
    COLORS = {
        'DEBUG': '\033[36m',     # Блакитний
        'INFO': '\033[32m',      # Зелений
        'WARNING': '\033[33m',   # Жовтий
        'ERROR': '\033[31m',     # Червоний
        'CRITICAL': '\033[41m',  # Червоний фон
        'RESET': '\033[0m'       # Скидання форматування
    }
    
    def format(self, record):
        # Зберігаємо оригінальний формат
        formatted = super().format(record)
        
        # Додаємо кольори для консольного виводу
        if record.levelname in self.COLORS:
            return f"{self.COLORS[record.levelname]}{formatted}{self.COLORS['RESET']}"
        return formatted


def setup_logging(config: Optional[Dict[str, Any]] = None) -> None:
    """
    Налаштування системи логування.
    
    :param config: Конфігурація логування. Якщо не вказано, використовується LOGGING_CONFIG.
    """
    if config is None:
        config = LOGGING_CONFIG
    
    # Отримуємо рівень логування
    log_level_str = config.get('level', 'INFO')
    log_level = getattr(logging, log_level_str) if isinstance(log_level_str, str) else log_level_str
    
    # Формат повідомлень
    log_format = config.get('format', '%(asctime)s - %(levelname)s - %(message)s')
    
    # Створюємо форматувальники
    standard_formatter = logging.Formatter(log_format)
    colored_formatter = ColoredFormatter(log_format)
    
    # Отримуємо список обробників
    handlers_list = config.get('handlers', ['console'])
    
    # Створюємо обробники
    handlers = []
    
    # Обробник для файлу
    if 'file' in handlers_list:
        file_path = config.get('file_path', 'scraping.log')
        
        # Створюємо директорію для логів, якщо її немає
        log_dir = os.path.dirname(file_path)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir)
            
        file_handler = logging.FileHandler(file_path, encoding='utf-8')
        file_handler.setFormatter(standard_formatter)
        handlers.append(file_handler)
    
    # Обробник для консолі
    if 'console' in handlers_list:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(colored_formatter if config.get('colored_console', True) else standard_formatter)
        handlers.append(console_handler)
    
    # Ротація файлів логів
    if 'rotating_file' in handlers_list:
        try:
            from logging.handlers import RotatingFileHandler
            
            file_path = config.get('file_path', 'scraping.log')
            max_bytes = config.get('max_bytes', 10485760)  # 10 MB
            backup_count = config.get('backup_count', 5)
            
            # Створюємо директорію для логів, якщо її немає
            log_dir = os.path.dirname(file_path)
            if log_dir and not os.path.exists(log_dir):
                os.makedirs(log_dir)
                
            rotating_handler = RotatingFileHandler(
                file_path, 
                maxBytes=max_bytes, 
                backupCount=backup_count,
                encoding='utf-8'
            )
            rotating_handler.setFormatter(standard_formatter)
            handlers.append(rotating_handler)
        except ImportError:
            print("Не вдалося створити RotatingFileHandler, використовуємо звичайний FileHandler")
            file_handler = logging.FileHandler(config.get('file_path', 'scraping.log'), encoding='utf-8')
            file_handler.setFormatter(standard_formatter)
            handlers.append(file_handler)
    
    # Логування за датою
    if 'timed_rotating_file' in handlers_list:
        try:
            from logging.handlers import TimedRotatingFileHandler
            
            file_path = config.get('file_path', 'scraping.log')
            when = config.get('when', 'midnight')
            interval = config.get('interval', 1)
            backup_count = config.get('backup_count', 30)
            
            # Створюємо директорію для логів, якщо її немає
            log_dir = os.path.dirname(file_path)
            if log_dir and not os.path.exists(log_dir):
                os.makedirs(log_dir)
                
            timed_handler = TimedRotatingFileHandler(
                file_path, 
                when=when, 
                interval=interval, 
                backupCount=backup_count,
                encoding='utf-8'
            )
            timed_handler.setFormatter(standard_formatter)
            handlers.append(timed_handler)
        except ImportError:
            print("Не вдалося створити TimedRotatingFileHandler, використовуємо звичайний FileHandler")
            file_handler = logging.FileHandler(config.get('file_path', 'scraping.log'), encoding='utf-8')
            file_handler.setFormatter(standard_formatter)
            handlers.append(file_handler)
    
    # Налаштовуємо кореневий логер
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    
    # Видаляємо наявні обробники
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Додаємо нові обробники
    for handler in handlers:
        root_logger.addHandler(handler)
    
    # Додаємо інформацію про початок логування
    logging.info(f"Логування ініціалізовано з рівнем {log_level_str}")


def get_logger(name: str) -> logging.Logger:
    """
    Отримання налаштованого логера для модуля.
    
    :param name: Назва логера (зазвичай __name__).
    :return: Налаштований логер.
    """
    return logging.getLogger(name) 