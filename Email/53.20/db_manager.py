"""
Управління базою даних для скрапера.
"""
import logging
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.ext.declarative import declarative_base
import asyncio
from typing import List, Dict, Any, Optional, Type, TypeVar, Generic, Union
from contextlib import contextmanager
import traceback
from datetime import datetime, UTC

from config import db_config
from models import Base, Company, CompanyData, KvedTracking, ScrapeJob, KvedStatus
from exceptions import DatabaseException

logger = logging.getLogger(__name__)
T = TypeVar('T', bound=Base)


class DatabaseManager:
    """Клас для управління базою даних."""
    
    def __init__(self):
        """Ініціалізація менеджера бази даних."""
        self.engine = None
        self.Session = None
        self._session_factory = None
        self.initialized = False
    
    def initialize(self):
        """Ініціалізація підключення до бази даних."""
        if self.initialized:
            return
            
        try:
            connection_string = db_config.get_connection_string()
            logger.info(f"Підключення до бази даних: {connection_string}")
            
            self.engine = sa.create_engine(connection_string)
            self._session_factory = sessionmaker(bind=self.engine)
            self.Session = scoped_session(self._session_factory)
            
            # Створення таблиць
            Base.metadata.create_all(self.engine)
            self.initialized = True
            logger.info("База даних ініціалізована успішно")
        except Exception as e:
            logger.error(f"Помилка при ініціалізації бази даних: {str(e)}")
            logger.debug(traceback.format_exc())
            raise DatabaseException("Не вдалося ініціалізувати базу даних", e)
    
    @contextmanager
    def session_scope(self):
        """Контекстний менеджер для сесій бази даних."""
        if not self.initialized:
            self.initialize()
            
        session = self.Session()
        try:
            yield session
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error(f"Помилка транзакції бази даних: {str(e)}")
            logger.debug(traceback.format_exc())
            raise DatabaseException("Помилка при роботі з базою даних", e)
        finally:
            session.close()
    
    def save_company(self, company_data: CompanyData, kved: str) -> int:
        """Збереження даних компанії в базу даних."""
        with self.session_scope() as session:
            # Перевіряємо, чи компанія вже існує (за назвою і КВЕДом)
            existing = session.query(Company).filter(
                sa.and_(
                    Company.name == company_data.name,
                    Company.kved == kved
                )
            ).first()
            
            if existing:
                # Оновлюємо існуючу компанію
                existing.address = company_data.address
                existing.phone = company_data.phone
                existing.email = company_data.email
                existing.updated_at = datetime.now(UTC)
                session.add(existing)
                return existing.id
            else:
                # Створюємо нову компанію
                company = Company.from_data_object(company_data, kved)
                session.add(company)
                session.flush()  # Щоб отримати ID
                return company.id
    
    def save_companies(self, companies_data: List[CompanyData], kved: str) -> int:
        """Пакетне збереження даних компаній в базу даних."""
        with self.session_scope() as session:
            saved_count = 0
            
            for company_data in companies_data:
                # Перевіряємо, чи компанія вже існує (за назвою і КВЕДом)
                existing = session.query(Company).filter(
                    sa.and_(
                        Company.name == company_data.name,
                        Company.kved == kved
                    )
                ).first()
                
                if existing:
                    # Оновлюємо існуючу компанію
                    existing.address = company_data.address
                    existing.phone = company_data.phone
                    existing.email = company_data.email
                    existing.updated_at = datetime.now(UTC)
                    session.add(existing)
                else:
                    # Створюємо нову компанію
                    company = Company.from_data_object(company_data, kved)
                    session.add(company)
                
                saved_count += 1
            
            return saved_count
    
    def get_companies_count(self, kved: Optional[str] = None) -> int:
        """Отримати кількість компаній в базі даних."""
        with self.session_scope() as session:
            query = session.query(sa.func.count(Company.id))
            if kved:
                query = query.filter(Company.kved == kved)
            return query.scalar() or 0
    
    def update_kved_status(self, kved: str, status: KvedStatus, 
                         processed_companies: Optional[int] = None,
                         last_page: Optional[int] = None,
                         total_companies: Optional[int] = None,
                         error_message: Optional[str] = None) -> None:
        """Оновити статус обробки КВЕДу."""
        with self.session_scope() as session:
            tracking = session.query(KvedTracking).filter(KvedTracking.kved == kved).first()
            
            if not tracking:
                # Створюємо новий запис відстеження
                tracking = KvedTracking(
                    kved=kved,
                    status=status.name,
                    total_companies=total_companies,
                    processed_companies=processed_companies or 0,
                    last_page_processed=last_page or 0,
                    started_at=datetime.now(UTC) if status == KvedStatus.IN_PROGRESS else None,
                    completed_at=datetime.now(UTC) if status in (KvedStatus.COMPLETED, KvedStatus.FAILED, KvedStatus.SKIPPED) else None,
                    error_message=error_message,
                    attempts=1
                )
            else:
                # Оновлюємо існуючий запис
                tracking.status = status.name
                if processed_companies is not None:
                    tracking.processed_companies = processed_companies
                if last_page is not None:
                    tracking.last_page_processed = last_page
                if total_companies is not None:
                    tracking.total_companies = total_companies
                if error_message is not None:
                    tracking.error_message = error_message
                
                # Оновлюємо часові мітки
                if status == KvedStatus.IN_PROGRESS and not tracking.started_at:
                    tracking.started_at = datetime.now(UTC)
                if status in (KvedStatus.COMPLETED, KvedStatus.FAILED, KvedStatus.SKIPPED):
                    tracking.completed_at = datetime.now(UTC)
                
                tracking.attempts += 1
            
            session.add(tracking)
    
    def get_kved_status(self, kved: str) -> Optional[Dict[str, Any]]:
        """Отримати інформацію про статус обробки КВЕДу."""
        with self.session_scope() as session:
            tracking = session.query(KvedTracking).filter(KvedTracking.kved == kved).first()
            
            if not tracking:
                return None
                
            return {
                'kved': tracking.kved,
                'status': tracking.status,
                'total_companies': tracking.total_companies,
                'processed_companies': tracking.processed_companies,
                'last_page_processed': tracking.last_page_processed,
                'started_at': tracking.started_at,
                'completed_at': tracking.completed_at,
                'error_message': tracking.error_message,
                'attempts': tracking.attempts
            }
    
    def create_scrape_job(self, kved: str, page: int) -> int:
        """Створити нове завдання скрапінгу."""
        with self.session_scope() as session:
            job = ScrapeJob(
                kved=kved,
                page=page,
                status='pending',
                created_at=datetime.now(UTC)
            )
            session.add(job)
            session.flush()
            return job.id
    
    def update_scrape_job(self, job_id: int, status: str, 
                         result: Optional[str] = None,
                         error_message: Optional[str] = None) -> None:
        """Оновити статус завдання скрапінгу."""
        with self.session_scope() as session:
            job = session.query(ScrapeJob).filter(ScrapeJob.id == job_id).first()
            
            if job:
                job.status = status
                if result:
                    job.result = result
                if error_message:
                    job.error_message = error_message
                
                if status == 'running' and not job.started_at:
                    job.started_at = datetime.now(UTC)
                elif status in ('completed', 'failed'):
                    job.completed_at = datetime.now(UTC)
                
                job.attempts += 1
                session.add(job)
    
    def get_pending_scrape_jobs(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Отримати список невиконаних завдань скрапінгу."""
        with self.session_scope() as session:
            jobs = session.query(ScrapeJob).filter(
                ScrapeJob.status == 'pending'
            ).order_by(
                ScrapeJob.created_at
            ).limit(limit).all()
            
            return [{
                'id': job.id,
                'kved': job.kved,
                'page': job.page,
                'status': job.status,
                'created_at': job.created_at,
                'attempts': job.attempts
            } for job in jobs]
    
    def close(self):
        """Закрити підключення до бази даних."""
        if self.engine:
            self.engine.dispose()
            logger.info("Підключення до бази даних закрито")


# Створюємо глобальний екземпляр менеджера БД
db_manager = DatabaseManager() 