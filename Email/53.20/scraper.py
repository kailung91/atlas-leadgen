"""
Основний модуль скрапера, який обробляє КВЕД та сторінки.
"""
import asyncio
import logging
import time
import random
from typing import List, Dict, Any, Optional, Tuple, Set
import traceback
from datetime import datetime, UTC
import os
import concurrent.futures
from urllib.parse import urljoin
import json
import signal
import sys
import atexit

from config import (
    scraper_config, http_config, timing_config, 
    concurrency_config, db_config, ensure_data_directory
)
from models import CompanyData, KvedStatus, ScraperProgress
from http_client import HttpClient
from parser import HtmlParser
from db_manager import db_manager
from lock_manager import LockManager
from exceptions import (
    ScraperException, HttpException, TooManyRequestsException, 
    PageNotFoundException, BlockedException, KvedSkipException,
    MaxRetriesExceededException, ScraperMaxFailuresException,
    LockException, DatabaseException, ParseException
)

logger = logging.getLogger(__name__)


class UARegionScraper:
    """
    Основний клас скрапера для ua-region.com.ua.
    """
    
    def __init__(self, kved: Optional[str] = None):
        """
        Ініціалізація скрапера.
        
        :param kved: КВЕД для скрапінгу. Якщо не вказано, буде використано КВЕД за замовчуванням.
        """
        self.kved = kved or "53.20"
        self.base_url = f"{scraper_config.base_url}/{self.kved}"
        
        # Шляхи до файлів з результатами
        self.output_csv = os.path.join(
            scraper_config.data_dir, 
            f"companies_{self.kved.replace('.', '_')}.csv"
        )
        
        # Прогрес скрапінгу
        self.progress = ScraperProgress(current_kved=self.kved)
        
        # Список оброблених сторінок
        self.processed_pages: Set[int] = set()
        
        # Лічильник послідовних невдач
        self.consecutive_failures = 0
        
        # Ініціалізація менеджера бази даних
        ensure_data_directory()
        db_manager.initialize()
        
        # Ініціалізація менеджера блокувань
        self.lock_manager = LockManager()
        
        # Реєстрація обробників для коректного завершення
        self._register_shutdown_handlers()
    
    def _register_shutdown_handlers(self) -> None:
        """Реєстрація обробників сигналів для коректного завершення."""
        atexit.register(self.cleanup)
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
    
    def _signal_handler(self, sig, frame) -> None:
        """Обробник сигналів для коректного завершення."""
        logger.info(f"Отримано сигнал {sig}. Виконую коректне завершення...")
        self.cleanup()
        sys.exit(0)
    
    def cleanup(self) -> None:
        """Функція для коректного завершення роботи скрапера."""
        try:
            if hasattr(self, 'progress') and self.progress.processed_companies > 0:
                logger.info(f"Зберігаю прогрес перед завершенням...")
                
                # Оновлюємо статус КВЕДу
                if hasattr(self, 'kved'):
                    db_manager.update_kved_status(
                        self.kved,
                        KvedStatus.IN_PROGRESS,
                        processed_companies=self.progress.processed_companies,
                        last_page=max(self.processed_pages) if self.processed_pages else 0,
                        total_companies=self.progress.total_companies
                    )
                
                # Виведення статистики
                if self.progress.start_time:
                    progress_info = self.progress.get_progress_info()
                    
                    if 'elapsed_time' in progress_info:
                        elapsed = progress_info['elapsed_time']
                        logger.info(
                            f"Загальний час роботи: "
                            f"{elapsed['hours']}г {elapsed['minutes']}хв {elapsed['seconds']}с"
                        )
                    
                    logger.info(f"Оброблено {self.progress.processed_companies} компаній")
        except Exception as e:
            logger.error(f"Помилка при завершенні роботи: {str(e)}")
    
    def _check_resume_point(self) -> int:
        """
        Перевірка наявності точки відновлення.
        
        :return: Номер сторінки, з якої потрібно продовжити скрапінг.
        """
        kved_status = db_manager.get_kved_status(self.kved)
        
        if kved_status and kved_status['status'] in (KvedStatus.IN_PROGRESS.name, KvedStatus.PENDING.name):
            last_page = kved_status.get('last_page_processed', 0)
            processed_companies = kved_status.get('processed_companies', 0)
            
            if last_page > 0:
                logger.info(f"Відновлення роботи з сторінки {last_page + 1} для КВЕДу {self.kved}")
                logger.info(f"Раніше оброблено {processed_companies} компаній")
                
                # Оновлюємо прогрес
                self.progress.processed_companies = processed_companies
                self.processed_pages = set(range(1, last_page + 1))
                
                return last_page + 1
        
        return 1
    
    async def _get_total_companies_and_pages(self) -> Tuple[int, int]:
        """
        Визначення загальної кількості компаній та сторінок.
        
        :return: Кортеж з кількістю компаній та кількістю сторінок.
        """
        async with HttpClient() as client:
            # Спочатку отримуємо першу сторінку для аналізу
            html, _ = await client.get_with_retry(f"{self.base_url}?start_page=1")
            
            # Визначаємо загальну кількість компаній
            total_companies = HtmlParser.get_total_companies(html)
            
            if not total_companies:
                logger.warning("Не вдалося визначити кількість компаній з HTML")
                total_companies = scraper_config.default_companies_count
            
            # Визначаємо загальну кількість сторінок
            total_pages = HtmlParser.get_total_pages(html)
            
            if not total_pages:
                logger.warning("Не вдалося визначити кількість сторінок з HTML")
                # Обчислюємо кількість сторінок на основі кількості компаній
                total_pages = (total_companies + scraper_config.companies_per_page - 1) // scraper_config.companies_per_page
                logger.info(f"Розраховано {total_pages} сторінок на основі {total_companies} компаній")
            
            return total_companies, total_pages
    
    async def process_page(self, page_num: int) -> List[CompanyData]:
        """
        Обробка однієї сторінки результатів.
        
        :param page_num: Номер сторінки для обробки.
        :return: Список знайдених компаній.
        :raises KvedSkipException: Якщо сторінку неможливо обробити і потрібно пропустити КВЕД.
        """
        url = f"{self.base_url}?start_page={page_num}"
        logger.info(f"Обробка сторінки {page_num}")
        
        try:
            async with HttpClient() as client:
                html, request_meta = await client.get_with_retry(url)
                
                # Перевірка на honeypot елементи
                if HtmlParser.parse_honeypot_elements(html):
                    logger.warning(f"Виявлено honeypot елементи на сторінці {page_num}. Робимо довгу паузу...")
                    await asyncio.sleep(random.uniform(180, 300))  # 3-5 хвилин
                
                # Перевірка на CAPTCHA
                if HtmlParser.check_captcha(html):
                    logger.error(f"Виявлено CAPTCHA на сторінці {page_num}!")
                    raise KvedSkipException(self.kved, "Виявлено CAPTCHA")
                
                # Парсинг компаній
                companies = HtmlParser.parse_companies_from_page(html)
                if not companies:
                    logger.warning(f"Не знайдено компаній на сторінці {page_num}")
                
                self.processed_pages.add(page_num)
                
                # Зберігаємо результати в базу даних
                if companies:
                    await self._save_companies_to_db(companies)
                    
                    # Оновлюємо прогрес
                    self.progress.processed_companies += len(companies)
                    self.progress.current_page = page_num
                    
                    # Логуємо прогрес
                    self._log_progress()
                
                # Оновлюємо статус у базі даних
                db_manager.update_kved_status(
                    self.kved,
                    KvedStatus.IN_PROGRESS,
                    processed_companies=self.progress.processed_companies,
                    last_page=page_num,
                    total_companies=self.progress.total_companies
                )
                
                self.consecutive_failures = 0  # Скидаємо лічильник при успіху
                
                return companies
                
        except (BlockedException, PageNotFoundException) as e:
            self.consecutive_failures += 1
            logger.error(f"{str(e)} на сторінці {page_num}")
            
            if self.consecutive_failures >= 2:
                logger.critical(f"Досягнуто ліміту послідовних невдач (2) для КВЕДу {self.kved}")
                raise KvedSkipException(self.kved, f"Помилка доступу до сторінки: {str(e)}")
            
            # Повертаємо порожній список, щоб сторінка була оброблена ще раз пізніше
            return []
            
        except MaxRetriesExceededException as e:
            self.consecutive_failures += 1
            logger.error(f"{str(e)}")
            
            if self.consecutive_failures >= 3:
                logger.critical(f"Досягнуто ліміту послідовних невдач (3) для КВЕДу {self.kved}")
                raise KvedSkipException(self.kved, f"Перевищено максимальну кількість спроб: {str(e)}")
            
            # Якщо ще не досягнуто ліміту, пропускаємо цю сторінку і переходимо до наступної
            return []
            
        except Exception as e:
            self.consecutive_failures += 1
            logger.error(f"Помилка при обробці сторінки {page_num}: {str(e)}")
            
            if self.consecutive_failures >= 3:
                logger.critical(f"Досягнуто ліміту послідовних невдач (3) для КВЕДу {self.kved}")
                raise KvedSkipException(self.kved, f"Неочікувана помилка: {str(e)}")
            
            # Якщо ще не досягнуто ліміту, пропускаємо цю сторінку і переходимо до наступної
            return []
    
    async def _save_companies_to_db(self, companies: List[CompanyData]) -> None:
        """
        Збереження компаній у базу даних.
        
        :param companies: Список компаній для збереження.
        """
        try:
            # Використовуємо ThreadPoolExecutor для виконання операцій з БД у окремому потоці
            with concurrent.futures.ThreadPoolExecutor() as executor:
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(
                    executor, 
                    db_manager.save_companies,
                    companies,
                    self.kved
                )
        except Exception as e:
            logger.error(f"Помилка при збереженні компаній у базу даних: {str(e)}")
            # Не піднімаємо виняток, щоб не переривати скрапінг
    
    def _log_progress(self) -> None:
        """Виведення інформації про прогрес."""
        if not self.progress.start_time or not self.progress.total_companies:
            return
            
        # Обчислюємо відсоток прогресу
        progress_percentage = self.progress.calculate_progress_percentage()
        
        # Оцінюємо залишковий час
        estimated_time_left = self.progress.calculate_estimated_time_left()
        
        if estimated_time_left is not None:
            hours, remainder = divmod(estimated_time_left, 3600)
            minutes, seconds = divmod(remainder, 60)
            
            # Логуємо кожні 20 компаній або при зміні сторінки
            if (self.progress.processed_companies % 20 == 0 or 
                self.progress.current_page not in self.processed_pages):
                logger.info(
                    f"Прогрес: {self.progress.processed_companies}/{self.progress.total_companies} " +
                    f"({progress_percentage:.2f}%). Сторінка {self.progress.current_page}/{self.progress.total_pages}. " +
                    f"Залишилось приблизно: {int(hours)}г {int(minutes)}хв {int(seconds)}с"
                )
    
    async def process_pages_concurrently(self, start_page: int, total_pages: int) -> None:
        """
        Обробка сторінок конкурентно з обмеженням кількості одночасних запитів.
        
        :param start_page: Номер сторінки, з якої починати обробку.
        :param total_pages: Загальна кількість сторінок.
        """
        # Створюємо семафор для обмеження кількості одночасних задач
        semaphore = asyncio.Semaphore(concurrency_config.semaphore_value)
        
        async def process_with_semaphore(page: int):
            async with semaphore:
                return await self.process_page(page)
        
        # Створюємо список завдань для всіх сторінок
        tasks = []
        for page_num in range(start_page, total_pages + 1):
            if page_num not in self.processed_pages:
                # Додаємо невелику затримку перед створенням нового завдання
                await asyncio.sleep(0.5)
                tasks.append(process_with_semaphore(page_num))
        
        # Виконуємо завдання і збираємо результати
        if tasks:
            # Використовуємо gather з return_exceptions=True, щоб не переривати інші завдання
            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            # Обробляємо результати
            for page_num, result in zip(range(start_page, total_pages + 1), results):
                if isinstance(result, Exception):
                    logger.error(f"Помилка при обробці сторінки {page_num}: {str(result)}")
                    if isinstance(result, KvedSkipException):
                        # Якщо отримано виняток пропуску КВЕДу, припиняємо обробку
                        logger.critical(f"Пропускаємо КВЕД {self.kved}: {result.reason}")
                        db_manager.update_kved_status(
                            self.kved,
                            KvedStatus.SKIPPED,
                            processed_companies=self.progress.processed_companies,
                            last_page=max(self.processed_pages) if self.processed_pages else 0,
                            total_companies=self.progress.total_companies,
                            error_message=result.reason
                        )
                        return
    
    async def run_async(self) -> bool:
        """
        Асинхронний запуск скрапінгу.
        
        :return: True у разі успішного завершення, False - у разі помилки.
        """
        logger.info(f"Початок збору даних для КВЕД {self.kved}...")
        self.progress.start_time = datetime.now(UTC)
        
        try:
            # Отримуємо кількість компаній та сторінок
            self.progress.total_companies, self.progress.total_pages = await self._get_total_companies_and_pages()
            logger.info(f"Знайдено {self.progress.total_companies} компаній на {self.progress.total_pages} сторінках")
            
            # Перевіряємо точку відновлення
            start_page = self._check_resume_point()
            
            # Оновлюємо статус КВЕДу
            db_manager.update_kved_status(
                self.kved,
                KvedStatus.IN_PROGRESS,
                processed_companies=self.progress.processed_companies,
                last_page=start_page - 1,
                total_companies=self.progress.total_companies
            )
            
            # Запускаємо обробку сторінок
            await self.process_pages_concurrently(start_page, self.progress.total_pages)
            
            # Перевіряємо, чи всі сторінки оброблено
            if len(self.processed_pages) >= self.progress.total_pages:
                logger.info(f"Усі сторінки для КВЕДу {self.kved} успішно оброблено")
                
                # Оновлюємо статус КВЕДу
                db_manager.update_kved_status(
                    self.kved,
                    KvedStatus.COMPLETED,
                    processed_companies=self.progress.processed_companies,
                    last_page=self.progress.total_pages,
                    total_companies=self.progress.total_companies
                )
                
                # Обчислюємо загальний час виконання
                total_time = (datetime.now(UTC) - self.progress.start_time).total_seconds()
                hours, remainder = divmod(total_time, 3600)
                minutes, seconds = divmod(remainder, 60)
                
                logger.info(f"Збір даних для КВЕДу {self.kved} завершено за {int(hours)}г {int(minutes)}хв {int(seconds)}с")
                logger.info(f"Зібрано {self.progress.processed_companies} компаній")
                
                return True
            else:
                # Якщо не всі сторінки оброблено, але немає виняткових ситуацій
                logger.warning(f"Не всі сторінки для КВЕДу {self.kved} оброблено. " +
                             f"Оброблено {len(self.processed_pages)} з {self.progress.total_pages}")
                
                # Оновлюємо статус КВЕДу
                db_manager.update_kved_status(
                    self.kved,
                    KvedStatus.IN_PROGRESS,
                    processed_companies=self.progress.processed_companies,
                    last_page=max(self.processed_pages) if self.processed_pages else 0,
                    total_companies=self.progress.total_companies
                )
                
                return False
        
        except KvedSkipException as e:
            logger.critical(f"Пропускаємо КВЕД {self.kved}: {e.reason}")
            
            # Оновлюємо статус КВЕДу
            db_manager.update_kved_status(
                self.kved,
                KvedStatus.SKIPPED,
                processed_companies=self.progress.processed_companies,
                last_page=max(self.processed_pages) if self.processed_pages else 0,
                total_companies=self.progress.total_companies,
                error_message=e.reason
            )
            
            return False
            
        except Exception as e:
            logger.critical(f"Критична помилка при скрапінгу КВЕДу {self.kved}: {str(e)}")
            logger.debug(traceback.format_exc())
            
            # Оновлюємо статус КВЕДу
            db_manager.update_kved_status(
                self.kved,
                KvedStatus.FAILED,
                processed_companies=self.progress.processed_companies,
                last_page=max(self.processed_pages) if self.processed_pages else 0,
                total_companies=self.progress.total_companies,
                error_message=str(e)
            )
            
            return False
    
    def run(self) -> bool:
        """
        Синхронний запуск скрапінгу (обгортка для асинхронного методу).
        
        :return: True у разі успішного завершення, False - у разі помилки.
        """
        try:
            # Перевіряємо, чи можна отримати блокування
            if not self.lock_manager.acquire_lock():
                logger.critical("Не вдалося отримати блокування. Можливо, скрапер вже запущений.")
                return False
            
            loop = asyncio.get_event_loop()
            return loop.run_until_complete(self.run_async())
        except Exception as e:
            logger.critical(f"Критична помилка при запуску скрапера: {str(e)}")
            logger.debug(traceback.format_exc())
            return False
        finally:
            # Звільняємо блокування
            self.lock_manager.release_lock()


class MultiKvedScraper:
    """
    Клас для запуску скрапінгу для декількох КВЕДів послідовно.
    """
    
    def __init__(self, kveds: Optional[List[str]] = None):
        """
        Ініціалізація мульти-скрапера.
        
        :param kveds: Список КВЕДів для скрапінгу. Якщо не вказано, буде використано список за замовчуванням.
        """
        from config import KVEDS
        self.kveds = kveds or KVEDS
        self.consecutive_failures = 0
        
        # Ініціалізація менеджера бази даних
        ensure_data_directory()
        db_manager.initialize()
    
    def is_kved_completed(self, kved: str) -> bool:
        """
        Перевірка, чи КВЕД вже оброблено.
        
        :param kved: КВЕД для перевірки.
        :return: True, якщо КВЕД вже оброблено, False - якщо ні.
        """
        status = db_manager.get_kved_status(kved)
        if status and status['status'] == KvedStatus.COMPLETED.name:
            companies_count = db_manager.get_companies_count(kved)
            if companies_count > 0:
                logger.info(f"КВЕД {kved} вже завантажено ({companies_count} компаній)")
                return True
        return False
    
    def run(self) -> None:
        """
        Запуск скрапінгу для всіх вказаних КВЕДів.
        """
        logger.info(f"Починаю збір даних для {len(self.kveds)} КВЕДів")
        
        # Створюємо список для відстеження завантажених КВЕДів
        completed_kveds = [kved for kved in self.kveds if self.is_kved_completed(kved)]
        
        logger.info(f"Завантажено {len(completed_kveds)} з {len(self.kveds)} КВЕДів")
        
        # Обробляємо КВЕДи в порядку їх визначення
        for kved in self.kveds:
            # Пропускаємо вже завантажені КВЕДи
            if kved in completed_kveds:
                continue
                
            logger.info(f"Обробка КВЕД {kved} ({len(completed_kveds) + 1}/{len(self.kveds)})")
            
            try:
                # Створюємо і запускаємо скрапер для поточного КВЕДу
                scraper = UARegionScraper(kved=kved)
                success = scraper.run()
                
                if success:
                    logger.info(f"Успішно завершено обробку КВЕД {kved}")
                    completed_kveds.append(kved)
                    self.consecutive_failures = 0  # Скидаємо лічильник при успіху
                else:
                    self.consecutive_failures += 1
                    logger.warning(f"Неповне завершення обробки КВЕД {kved}. Послідовних невдач: {self.consecutive_failures}")
                    
                    if self.consecutive_failures >= 3:
                        logger.critical(f"Досягнуто ліміту послідовних невдач для КВЕДів (3). Завершення роботи...")
                        break
                
                # Перевіряємо ще раз, чи було успішно завантажено
                if self.is_kved_completed(kved) and kved not in completed_kveds:
                    completed_kveds.append(kved)
                    logger.info(f"КВЕД {kved} підтверджено як завантажений")
                
                # Пауза між обробкою різних КВЕДів
                pause_time = random.uniform(60, 180)  # 1-3 хвилини
                logger.info(f"Пауза між КВЕДами: {pause_time:.0f} секунд")
                time.sleep(pause_time)
                
            except Exception as e:
                self.consecutive_failures += 1
                logger.error(f"Помилка при обробці КВЕД {kved}: {str(e)}")
                
                if self.consecutive_failures >= 3:
                    logger.critical(f"Досягнуто ліміту послідовних невдач для КВЕДів (3). Завершення роботи...")
                    break
        
        logger.info(f"Збір даних для всіх КВЕДів завершено. Оброблено {len(completed_kveds)} з {len(self.kveds)} КВЕДів.")


# Функція для запуску скрапінгу для одного КВЕДу
def scrape_kved(kved: str) -> bool:
    """
    Запуск скрапінгу для одного КВЕДу.
    
    :param kved: КВЕД для скрапінгу.
    :return: True у разі успішного завершення, False - у разі помилки.
    """
    try:
        scraper = UARegionScraper(kved=kved)
        return scraper.run()
    except Exception as e:
        logger.critical(f"Критична помилка при скрапінгу КВЕДу {kved}: {str(e)}")
        logger.debug(traceback.format_exc())
        return False


# Функція для запуску скрапінгу для всіх КВЕДів
def scrape_all_kveds(kveds: Optional[List[str]] = None) -> None:
    """
    Запуск скрапінгу для всіх КВЕДів.
    
    :param kveds: Список КВЕДів для скрапінгу. Якщо не вказано, буде використано список за замовчуванням.
    """
    try:
        scraper = MultiKvedScraper(kveds=kveds)
        scraper.run()
    except Exception as e:
        logger.critical(f"Критична помилка при скрапінгу всіх КВЕДів: {str(e)}")
        logger.debug(traceback.format_exc()) 