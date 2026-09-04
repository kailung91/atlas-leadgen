"""
Файл конфігурації для скрапера.
"""
import logging
import os
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum

# Налаштування логування
LOGGING_CONFIG = {
    'level': 'INFO',
    'format': '%(asctime)s - %(levelname)s - %(message)s',
    'handlers': [
        'file',
        'console'
    ],
    'file_path': "scraping.log"
}

# Параметри HTTP запитів
@dataclass
class HttpConfig:
    max_retries: int = 5
    base_timeout: int = 30
    max_timeout: int = 120
    user_agents: List[str] = None
    
    def __post_init__(self):
        if self.user_agents is None:
            self.user_agents = [
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:122.0) Gecko/20100101 Firefox/122.0',
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Safari/605.1.15',
                'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Edge/121.0.0.0',
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0',
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36',
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 OPR/107.0.0.0',
                'Mozilla/5.0 (iPad; CPU OS 17_3 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.3 Mobile/15E148 Safari/604.1'
            ]

# Базові параметри скрапера
@dataclass
class ScraperConfig:
    base_url: str = "https://www.ua-region.com.ua/kved"
    companies_per_page: int = 20
    default_companies_count: int = 20000
    default_pages_count: int = 2000
    data_dir: str = "data"
    lock_file: str = "scraper.lock"

# Таймінги та затримки
@dataclass
class TimingConfig:
    min_delay: float = 5.0
    max_delay: float = 10.0
    chance_long_delay: float = 0.2
    long_delay_min: float = 15.0
    long_delay_max: float = 25.0
    chance_very_long_delay: float = 0.1
    very_long_delay_min: float = 60.0
    very_long_delay_max: float = 120.0
    backoff_factor: float = 1.5
    backoff_max: float = 300.0

# Параметри конкурентності
@dataclass
class ConcurrencyConfig:
    max_workers: int = 3
    max_connections: int = 5
    semaphore_value: int = 3

# Параметри бази даних
class DatabaseType(Enum):
    SQLITE = "sqlite"
    POSTGRESQL = "postgresql"

@dataclass
class DatabaseConfig:
    db_type: DatabaseType = DatabaseType.SQLITE
    db_path: str = "companies.db"
    host: Optional[str] = None
    port: Optional[int] = None
    user: Optional[str] = None
    password: Optional[str] = None
    db_name: Optional[str] = None
    
    def get_connection_string(self) -> str:
        if self.db_type == DatabaseType.SQLITE:
            return f"sqlite:///{self.db_path}"
        elif self.db_type == DatabaseType.POSTGRESQL:
            return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.db_name}"
        else:
            raise ValueError(f"Непідтримуваний тип бази даних: {self.db_type}")

# Список КВЕДів для скрапінгу
KVEDS = [
    # Освіта
    "85.10", "85.20", "85.31", "85.32", "85.40", "85.42", "85.59",
    # Транспорт
    "49.41", "49.42", "53.20", "49.31", "49.39",
    # Туризм
    "79.11", "55.10", "79.90",
    # Музеї
    "91.02", "91.03",
    # Нерухомість
    "41.10", "41.20", "68.10", "71.11", "68.31",
    # Державне управління
    "84.11", "84.12",
    # Видавництво
    "58.11", "58.12", "58.19", "58.13", "58.14",
    # Роздрібна торгівля
    "47.61", "47.78", "47.62",
    # Сільське господарство
    "01.1", "01.2", "01.3", "01.4", "01.5", "01.6", "01.7"
]

# Створення екземплярів конфігурацій за замовчуванням
http_config = HttpConfig()
scraper_config = ScraperConfig()
timing_config = TimingConfig()
concurrency_config = ConcurrencyConfig()
db_config = DatabaseConfig()

def ensure_data_directory() -> None:
    """Забезпечити існування директорії для даних"""
    if not os.path.exists(scraper_config.data_dir):
        os.makedirs(scraper_config.data_dir) 