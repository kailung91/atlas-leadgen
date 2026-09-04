"""
Асинхронний HTTP клієнт з експоненційними затримками та механізмом повторних спроб.
"""
import aiohttp
import asyncio
import random
import logging
import time
from typing import Dict, Optional, Any, Union, Tuple
import traceback

from config import http_config, timing_config
from exceptions import (
    HttpException, TooManyRequestsException, PageNotFoundException,
    BlockedException, MaxRetriesExceededException
)

logger = logging.getLogger(__name__)


class HttpClient:
    """
    Клас для асинхронних HTTP запитів з керуванням повторними спробами та затримками.
    """
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.current_user_agent = random.choice(http_config.user_agents)
        self.headers = {
            'User-Agent': self.current_user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'uk-UA,uk;q=0.9,en-US;q=0.8,en;q=0.7',
            'Referer': 'https://www.ua-region.com.ua/',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'max-age=0',
        }
        self.cookies = {}
        self.consecutive_failures = 0
        
    async def create_session(self) -> None:
        """Створити нову HTTP сесію."""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                headers=self.headers,
                cookies=self.cookies,
                timeout=aiohttp.ClientTimeout(total=http_config.base_timeout)
            )

    async def close_session(self) -> None:
        """Закрити HTTP сесію."""
        if self.session and not self.session.closed:
            await self.session.close()
            self.session = None
    
    def rotate_user_agent(self) -> None:
        """Змінити User-Agent на випадковий з доступного списку."""
        new_agent = random.choice(http_config.user_agents)
        while new_agent == self.current_user_agent and len(http_config.user_agents) > 1:
            new_agent = random.choice(http_config.user_agents)
            
        self.current_user_agent = new_agent
        self.headers['User-Agent'] = new_agent
        logger.info(f"User-Agent змінено на: {new_agent}")
    
    async def human_like_delay(self) -> float:
        """Затримка, що імітує людську поведінку."""
        # Основна затримка
        delay = random.uniform(timing_config.min_delay, timing_config.max_delay)
        
        # З певним шансом збільшуємо затримку
        if random.random() < timing_config.chance_long_delay:
            delay += random.uniform(timing_config.long_delay_min, timing_config.long_delay_max)
            
        # З певним шансом робимо дуже велику паузу
        if random.random() < timing_config.chance_very_long_delay:
            delay += random.uniform(timing_config.very_long_delay_min, timing_config.very_long_delay_max)
            logger.info(f"Довга пауза на {delay:.2f} секунд...")
        
        # Виконуємо затримку
        await asyncio.sleep(delay)
        return delay
    
    async def get_with_retry(self, url: str, params: Optional[Dict] = None) -> Tuple[str, Dict[str, Any]]:
        """
        Виконати GET запит з повторними спробами у випадку помилок.
        Використовує експоненційний backoff для затримок між спробами.
        """
        await self.create_session()
        
        retry_delay = timing_config.min_delay
        metadata = {"attempts": 0, "total_delay": 0}
        
        for attempt in range(http_config.max_retries):
            metadata["attempts"] += 1
            
            try:
                # Затримка перед запитом
                delay = await self.human_like_delay()
                metadata["total_delay"] += delay
                
                logger.info(f"Спроба {attempt+1}: Запит до {url} (затримка {delay:.2f}с)")
                
                async with self.session.get(url, params=params) as response:
                    # Зберігаємо cookies для подальших запитів
                    self.cookies.update(response.cookies)
                    
                    # Обробка різних статус-кодів
                    if response.status == 200:
                        logger.info(f"Успішно отримано сторінку {url}")
                        self.consecutive_failures = 0  # Скидаємо лічильник невдач при успіху
                        return await response.text(), metadata
                    
                    elif response.status == 403 or response.status == 429:
                        # Забагато запитів або доступ заборонено
                        wait_time = min(retry_delay * timing_config.backoff_factor, timing_config.backoff_max)
                        logger.warning(
                            f"Отримано код {response.status}. "
                            f"Чекаємо {wait_time:.0f} секунд перед повторною спробою..."
                        )
                        await asyncio.sleep(wait_time)
                        retry_delay = wait_time  # Збільшуємо затримку для наступної спроби
                        
                        # Оновлюємо User-Agent
                        self.rotate_user_agent()
                        
                        # Перевіряємо на блокування
                        if attempt >= 2:  # Якщо це вже третя спроба з помилкою доступу
                            raise BlockedException(
                                "Можливе блокування доступу до сайту", 
                                status_code=response.status, 
                                url=url
                            )
                    
                    elif response.status == 404:
                        # Сторінка не знайдена
                        if attempt >= 1:  # Це вже друга спроба
                            raise PageNotFoundException(
                                "Сторінка не існує", 
                                status_code=404, 
                                url=url
                            )
                        else:
                            logger.warning(f"Отримано код 404 для {url}. Спробуємо ще раз...")
                            await asyncio.sleep(retry_delay)
                    
                    else:
                        # Інші помилки
                        logger.error(f"Помилка {response.status} при запиті {url}")
                        await asyncio.sleep(retry_delay)
                        retry_delay = min(retry_delay * timing_config.backoff_factor, timing_config.backoff_max)
            
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                logger.error(f"Помилка з'єднання при запиті {url}: {str(e)}")
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * timing_config.backoff_factor, timing_config.backoff_max)
            
            except (BlockedException, PageNotFoundException) as e:
                # Ці винятки прокидаємо далі
                raise
            
            except Exception as e:
                logger.error(f"Неочікувана помилка при запиті {url}: {str(e)}")
                logger.debug(traceback.format_exc())
                await asyncio.sleep(retry_delay)
                retry_delay = min(retry_delay * timing_config.backoff_factor, timing_config.backoff_max)
        
        # Якщо досягли цього місця, значить вичерпали всі спроби
        self.consecutive_failures += 1
        
        raise MaxRetriesExceededException(f"Не вдалося отримати сторінку {url} після {http_config.max_retries} спроб")
        
    async def __aenter__(self):
        await self.create_session()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close_session() 