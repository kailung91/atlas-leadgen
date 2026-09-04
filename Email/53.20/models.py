"""
Моделі даних для скрапера.
"""
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any
from datetime import datetime, UTC
from enum import Enum, auto
import sqlalchemy as sa
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


@dataclass
class CompanyData:
    """Дані про компанію."""
    name: str
    address: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Конвертувати в словник."""
        return {
            'Назва': self.name,
            'Адреса': self.address or '',
            'Телефон': self.phone or '',
            'Email': self.email or ''
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CompanyData':
        """Створити об'єкт з словника."""
        return cls(
            name=data.get('Назва', ''),
            address=data.get('Адреса', ''),
            phone=data.get('Телефон', ''),
            email=data.get('Email', '')
        )


class Company(Base):
    """Модель компанії для бази даних."""
    __tablename__ = 'companies'
    
    id = sa.Column(sa.Integer, primary_key=True)
    name = sa.Column(sa.String(255), nullable=False)
    address = sa.Column(sa.String(512), nullable=True)
    phone = sa.Column(sa.String(255), nullable=True)
    email = sa.Column(sa.String(255), nullable=True)
    kved = sa.Column(sa.String(10), nullable=False, index=True)
    created_at = sa.Column(sa.DateTime, default=datetime.utcnow)
    updated_at = sa.Column(sa.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    def to_data_object(self) -> CompanyData:
        """Конвертувати в об'єкт даних."""
        return CompanyData(
            name=self.name,
            address=self.address,
            phone=self.phone,
            email=self.email
        )
    
    @classmethod
    def from_data_object(cls, data: CompanyData, kved: str) -> 'Company':
        """Створити об'єкт моделі з об'єкта даних."""
        return cls(
            name=data.name,
            address=data.address,
            phone=data.phone,
            email=data.email,
            kved=kved
        )


class KvedStatus(Enum):
    """Статус обробки КВЕДу."""
    PENDING = auto()
    IN_PROGRESS = auto()
    COMPLETED = auto()
    FAILED = auto()
    SKIPPED = auto()


class KvedTracking(Base):
    """Модель для відстеження статусу обробки КВЕДів."""
    __tablename__ = 'kved_tracking'
    
    kved = sa.Column(sa.String(10), primary_key=True)
    status = sa.Column(sa.String(20), nullable=False, default=KvedStatus.PENDING.name)
    total_companies = sa.Column(sa.Integer, nullable=True)
    processed_companies = sa.Column(sa.Integer, nullable=False, default=0)
    last_page_processed = sa.Column(sa.Integer, nullable=False, default=0)
    started_at = sa.Column(sa.DateTime, nullable=True)
    completed_at = sa.Column(sa.DateTime, nullable=True)
    error_message = sa.Column(sa.Text, nullable=True)
    attempts = sa.Column(sa.Integer, nullable=False, default=0)
    
    def __repr__(self) -> str:
        return f"<KvedTracking(kved='{self.kved}', status='{self.status}', processed={self.processed_companies})>"


class ScrapeJob(Base):
    """Модель для відстеження завдань скрапінгу."""
    __tablename__ = 'scrape_jobs'
    
    id = sa.Column(sa.Integer, primary_key=True)
    kved = sa.Column(sa.String(10), nullable=False, index=True)
    page = sa.Column(sa.Integer, nullable=False)
    status = sa.Column(sa.String(20), nullable=False, default='pending')
    result = sa.Column(sa.Text, nullable=True)
    created_at = sa.Column(sa.DateTime, default=datetime.utcnow)
    started_at = sa.Column(sa.DateTime, nullable=True)
    completed_at = sa.Column(sa.DateTime, nullable=True)
    attempts = sa.Column(sa.Integer, nullable=False, default=0)
    error_message = sa.Column(sa.Text, nullable=True)
    
    def __repr__(self) -> str:
        return f"<ScrapeJob(id={self.id}, kved='{self.kved}', page={self.page}, status='{self.status}')>"


@dataclass
class ScraperProgress:
    """Клас для відстеження прогресу скрапінгу."""
    total_companies: int = 0
    processed_companies: int = 0
    start_time: Optional[datetime] = None
    current_kved: Optional[str] = None
    current_page: int = 0
    total_pages: int = 0
    
    def calculate_progress_percentage(self) -> float:
        """Розрахувати відсоток прогресу."""
        if self.total_companies <= 0:
            return 0.0
        return (self.processed_companies / self.total_companies) * 100
    
    def calculate_estimated_time_left(self) -> Optional[float]:
        """Розрахувати орієнтовний час, що залишився (в секундах)."""
        if (self.start_time is None or 
            self.processed_companies <= 0 or 
            self.total_companies <= 0):
            return None
        
        elapsed_seconds = (datetime.now(UTC) - self.start_time).total_seconds()
        time_per_company = elapsed_seconds / self.processed_companies
        remaining_companies = self.total_companies - self.processed_companies
        return remaining_companies * time_per_company
    
    def get_progress_info(self) -> Dict[str, Any]:
        """Отримати інформацію про прогрес у вигляді словника."""
        result = {
            'processed_companies': self.processed_companies,
            'total_companies': self.total_companies,
            'progress_percentage': self.calculate_progress_percentage(),
            'current_kved': self.current_kved,
            'current_page': self.current_page,
            'total_pages': self.total_pages
        }
        
        estimated_time = self.calculate_estimated_time_left()
        if estimated_time is not None:
            hours, remainder = divmod(estimated_time, 3600)
            minutes, seconds = divmod(remainder, 60)
            result['estimated_time_left'] = {
                'hours': int(hours),
                'minutes': int(minutes),
                'seconds': int(seconds),
                'total_seconds': estimated_time
            }
        
        if self.start_time is not None:
            elapsed_time = (datetime.now(UTC) - self.start_time).total_seconds()
            hours, remainder = divmod(elapsed_time, 3600)
            minutes, seconds = divmod(remainder, 60)
            result['elapsed_time'] = {
                'hours': int(hours),
                'minutes': int(minutes),
                'seconds': int(seconds),
                'total_seconds': elapsed_time
            }
        
        return result 