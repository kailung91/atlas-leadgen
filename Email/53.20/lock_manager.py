"""
Менеджер блокувань для запобігання одночасному запуску кількох екземплярів скрапера.
"""
import os
import time
import logging
import atexit
import socket
import platform
import msvcrt
from typing import Optional

from config import scraper_config
from exceptions import LockException

logger = logging.getLogger(__name__)


class LockManager:
    """
    Клас для створення та керування блокуваннями файлів.
    Запобігає одночасному запуску кількох екземплярів скрапера.
    
    Реалізація сумісна з Windows і Unix-подібними системами.
    """
    
    def __init__(self, lock_file: Optional[str] = None):
        """
        Ініціалізація менеджера блокувань.
        
        :param lock_file: Шлях до файлу блокування. Якщо не вказано, використовується шлях за замовчуванням.
        """
        self.lock_file = lock_file or scraper_config.lock_file
        self.lock_acquired = False
        self.lock_fd = None
        self.system = platform.system()
        
        # Реєстрація обробника для звільнення блокування при виході
        atexit.register(self.release_lock)
    
    def acquire_lock(self) -> bool:
        """
        Спроба отримати блокування.
        
        :return: True, якщо блокування успішно отримане, False - якщо ні.
        :raises LockException: якщо виникла помилка при спробі отримати блокування.
        """
        try:
            # Створюємо файл блокування, якщо його немає
            if self.system == 'Windows':
                # Windows-специфічна реалізація
                try:
                    # Пробуємо відкрити файл в режимі "w+", який створить файл, якщо він не існує
                    # і переписати його, якщо він існує
                    self.lock_fd = open(self.lock_file, 'w+')
                    
                    # Спроба встановити ексклюзивний доступ до файлу
                    # msvcrt.locking потрібний хендл файлу, а не файловий об'єкт
                    file_handle = msvcrt.get_osfhandle(self.lock_fd.fileno())
                    msvcrt.locking(self.lock_fd.fileno(), msvcrt.LK_NBLCK, 1)
                    
                    # Записуємо інформацію про поточний процес у файл блокування
                    hostname = socket.gethostname()
                    pid = os.getpid()
                    timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
                    
                    self.lock_fd.seek(0)
                    self.lock_fd.truncate()
                    self.lock_fd.write(f"PID: {pid}\nHost: {hostname}\nStarted: {timestamp}\n")
                    self.lock_fd.flush()
                    
                    self.lock_acquired = True
                    logger.info(f"Блокування отримано: {self.lock_file} (PID: {pid})")
                    return True
                except (IOError, PermissionError) as e:
                    # Якщо файл уже заблокований, закриваємо дескриптор
                    if self.lock_fd:
                        self.lock_fd.close()
                        self.lock_fd = None
                    logger.warning(f"Не вдалося отримати блокування: файл вже заблокований іншим процесом")
                    return False
            else:
                # Unix-подібна реалізація (використовується fcntl)
                import fcntl
                
                self.lock_fd = open(self.lock_file, 'w')
                
                # Спроба блокування файлу
                fcntl.flock(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                
                # Записуємо інформацію про поточний процес у файл блокування
                hostname = socket.gethostname()
                pid = os.getpid()
                timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
                
                self.lock_fd.seek(0)
                self.lock_fd.truncate()
                self.lock_fd.write(f"PID: {pid}\nHost: {hostname}\nStarted: {timestamp}\n")
                self.lock_fd.flush()
                
                self.lock_acquired = True
                logger.info(f"Блокування отримано: {self.lock_file} (PID: {pid})")
                return True
            
        except Exception as e:
            if self.lock_fd:
                self.lock_fd.close()
                self.lock_fd = None
            logger.error(f"Неочікувана помилка при спробі отримати блокування: {str(e)}")
            raise LockException(f"Неочікувана помилка блокування: {str(e)}")
    
    def check_lock(self) -> bool:
        """
        Перевірка, чи заблоковано файл іншим процесом.
        
        :return: True, якщо файл заблокований, False - якщо ні.
        """
        if not os.path.exists(self.lock_file):
            return False
            
        try:
            if self.system == 'Windows':
                # Windows-специфічна реалізація
                try:
                    with open(self.lock_file, 'r+') as f:
                        file_handle = msvcrt.get_osfhandle(f.fileno())
                        try:
                            # Спробуємо заблокувати файл. Якщо він вже заблокований, буде виняток
                            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
                            # Якщо блокування успішне, одразу знімаємо його
                            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
                            # Якщо ми дійшли сюди, значить файл не був заблокований
                            return False
                        except (IOError, PermissionError):
                            # Файл заблокований
                            return True
                except (IOError, PermissionError):
                    # Файл не можна відкрити, вважаємо, що він заблокований
                    return True
            else:
                # Unix-подібна реалізація
                import fcntl
                
                with open(self.lock_file, 'r') as f:
                    try:
                        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        # Якщо блокування успішне, одразу знімаємо його
                        fcntl.flock(f, fcntl.LOCK_UN)
                        return False
                    except IOError:
                        # Файл заблокований
                        return True
        except Exception:
            # У випадку інших помилок, припускаємо, що файл не заблокований
            return False
    
    def release_lock(self) -> None:
        """
        Звільнення блокування.
        """
        if self.lock_acquired and self.lock_fd:
            try:
                if self.system == 'Windows':
                    # Windows-специфічна реалізація
                    msvcrt.locking(self.lock_fd.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    # Unix-подібна реалізація
                    import fcntl
                    fcntl.flock(self.lock_fd, fcntl.LOCK_UN)
                
                self.lock_fd.close()
                self.lock_acquired = False
                logger.info(f"Блокування звільнено: {self.lock_file}")
            except Exception as e:
                logger.error(f"Помилка при звільненні блокування: {str(e)}")
    
    def __enter__(self):
        """
        Контекстний менеджер для використання з 'with'.
        """
        if not self.acquire_lock():
            raise LockException("Не вдалося отримати блокування - можливо, скрапер вже запущений")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Звільнення блокування при виході з контексту.
        """
        self.release_lock() 