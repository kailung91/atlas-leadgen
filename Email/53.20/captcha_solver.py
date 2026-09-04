"""
Модуль для розпізнавання та вирішення CAPTCHA.
"""
import logging
import base64
import json
import aiohttp
import asyncio
from typing import Optional, Dict, Any, Union, Tuple
import os
import time
import traceback
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass

from exceptions import ScraperException

logger = logging.getLogger(__name__)


class CaptchaException(ScraperException):
    """Базовий клас для винятків, пов'язаних з CAPTCHA."""
    pass


class CaptchaApiException(CaptchaException):
    """Виняток для помилок API сервісу розпізнавання CAPTCHA."""
    pass


class CaptchaTimeoutException(CaptchaException):
    """Виняток для таймаутів при розпізнаванні CAPTCHA."""
    pass


class CaptchaSolveException(CaptchaException):
    """Виняток для помилок при розв'язанні CAPTCHA."""
    pass


@dataclass
class CaptchaTask:
    """Завдання на розпізнавання CAPTCHA."""
    task_id: str
    created_at: float = time.time()
    result: Optional[str] = None
    status: str = "pending"


class CaptchaSolverBase(ABC):
    """Базовий клас для сервісів розпізнавання CAPTCHA."""
    
    @abstractmethod
    async def solve_image_captcha(self, image_data: Union[str, bytes]) -> str:
        """
        Розпізнати CAPTCHA з зображення.
        
        :param image_data: Дані зображення у вигляді шляху до файлу, URL або байтів.
        :return: Розпізнаний текст CAPTCHA.
        """
        pass
    
    @abstractmethod
    async def solve_recaptcha(self, site_key: str, page_url: str) -> str:
        """
        Розпізнати reCAPTCHA.
        
        :param site_key: Ключ сайту для reCAPTCHA.
        :param page_url: URL сторінки, на якій розташована CAPTCHA.
        :return: Токен reCAPTCHA.
        """
        pass
    
    @abstractmethod
    async def solve_hcaptcha(self, site_key: str, page_url: str) -> str:
        """
        Розпізнати hCaptcha.
        
        :param site_key: Ключ сайту для hCaptcha.
        :param page_url: URL сторінки, на якій розташована CAPTCHA.
        :return: Токен hCaptcha.
        """
        pass


class TwoCaptchaSolver(CaptchaSolverBase):
    """Клас для взаємодії з сервісом 2captcha.com."""
    
    def __init__(self, api_key: str):
        """
        Ініціалізація клієнта 2captcha.
        
        :param api_key: API ключ для 2captcha.com.
        """
        self.api_key = api_key
        self.base_url = "https://2captcha.com/api"
        self.check_interval = 5  # Інтервал перевірки в секундах
        self.max_wait_time = 120  # Максимальний час очікування в секундах
    
    async def _request(self, endpoint: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Виконати запит до API 2captcha.
        
        :param endpoint: Кінцева точка API.
        :param params: Параметри запиту.
        :return: Відповідь від API у вигляді словника.
        """
        params['key'] = self.api_key
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.base_url}/{endpoint}", data=params) as response:
                    if response.status != 200:
                        raise CaptchaApiException(f"Помилка API 2captcha: {response.status}")
                    
                    result = await response.text()
                    
                    if result.startswith('ERROR'):
                        raise CaptchaApiException(f"Помилка API 2captcha: {result}")
                    
                    # Перевіряємо, чи відповідь у форматі JSON
                    try:
                        return json.loads(result)
                    except json.JSONDecodeError:
                        # Якщо не JSON, повертаємо як є
                        return {"result": result}
        except aiohttp.ClientError as e:
            raise CaptchaApiException(f"Помилка з'єднання з 2captcha: {str(e)}")
    
    async def _wait_for_result(self, task_id: str) -> str:
        """
        Очікування результату розпізнавання CAPTCHA.
        
        :param task_id: ID завдання.
        :return: Розпізнаний текст CAPTCHA.
        """
        start_time = time.time()
        
        while time.time() - start_time < self.max_wait_time:
            await asyncio.sleep(self.check_interval)
            
            try:
                params = {
                    'action': 'get',
                    'id': task_id
                }
                
                result = await self._request('res.php', params)
                
                if result['result'] == 'CAPCHA_NOT_READY':
                    continue
                
                return result['result']
            except CaptchaApiException as e:
                logger.error(f"Помилка при перевірці статусу CAPTCHA: {str(e)}")
                # Продовжуємо очікування у випадку помилки API
        
        raise CaptchaTimeoutException(f"Таймаут при очікуванні результату CAPTCHA")
    
    async def solve_image_captcha(self, image_data: Union[str, bytes]) -> str:
        """
        Розпізнати CAPTCHA з зображення.
        
        :param image_data: Дані зображення у вигляді шляху до файлу, URL або байтів.
        :return: Розпізнаний текст CAPTCHA.
        """
        params = {
            'method': 'post'
        }
        
        # Визначаємо тип вхідних даних
        if isinstance(image_data, str):
            if image_data.startswith('http'):
                # URL зображення
                params['body'] = image_data
            else:
                # Шлях до файлу
                try:
                    with open(image_data, 'rb') as f:
                        image_bytes = f.read()
                    params['body'] = base64.b64encode(image_bytes).decode('utf-8')
                except Exception as e:
                    raise CaptchaSolveException(f"Помилка при читанні файлу зображення: {str(e)}")
        else:
            # Байти зображення
            params['body'] = base64.b64encode(image_data).decode('utf-8')
        
        try:
            # Відправляємо завдання
            result = await self._request('in.php', params)
            task_id = result['result'].split('|')[1]
            
            # Очікуємо результат
            return await self._wait_for_result(task_id)
        except Exception as e:
            raise CaptchaSolveException(f"Помилка при розпізнаванні CAPTCHA: {str(e)}")
    
    async def solve_recaptcha(self, site_key: str, page_url: str) -> str:
        """
        Розпізнати reCAPTCHA.
        
        :param site_key: Ключ сайту для reCAPTCHA.
        :param page_url: URL сторінки, на якій розташована CAPTCHA.
        :return: Токен reCAPTCHA.
        """
        params = {
            'method': 'userrecaptcha',
            'googlekey': site_key,
            'pageurl': page_url
        }
        
        try:
            # Відправляємо завдання
            result = await self._request('in.php', params)
            task_id = result['result'].split('|')[1]
            
            # Очікуємо результат
            return await self._wait_for_result(task_id)
        except Exception as e:
            raise CaptchaSolveException(f"Помилка при розпізнаванні reCAPTCHA: {str(e)}")
    
    async def solve_hcaptcha(self, site_key: str, page_url: str) -> str:
        """
        Розпізнати hCaptcha.
        
        :param site_key: Ключ сайту для hCaptcha.
        :param page_url: URL сторінки, на якій розташована CAPTCHA.
        :return: Токен hCaptcha.
        """
        params = {
            'method': 'hcaptcha',
            'sitekey': site_key,
            'pageurl': page_url
        }
        
        try:
            # Відправляємо завдання
            result = await self._request('in.php', params)
            task_id = result['result'].split('|')[1]
            
            # Очікуємо результат
            return await self._wait_for_result(task_id)
        except Exception as e:
            raise CaptchaSolveException(f"Помилка при розпізнаванні hCaptcha: {str(e)}")


class AntiCaptchaSolver(CaptchaSolverBase):
    """Клас для взаємодії з сервісом anti-captcha.com."""
    
    def __init__(self, api_key: str):
        """
        Ініціалізація клієнта Anti-Captcha.
        
        :param api_key: API ключ для anti-captcha.com.
        """
        self.api_key = api_key
        self.base_url = "https://api.anti-captcha.com"
        self.check_interval = 5  # Інтервал перевірки в секундах
        self.max_wait_time = 120  # Максимальний час очікування в секундах
    
    async def _request(self, endpoint: str, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Виконати запит до API Anti-Captcha.
        
        :param endpoint: Кінцева точка API.
        :param data: Дані запиту.
        :return: Відповідь від API у вигляді словника.
        """
        data['clientKey'] = self.api_key
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.base_url}/{endpoint}", json=data) as response:
                    if response.status != 200:
                        raise CaptchaApiException(f"Помилка API Anti-Captcha: {response.status}")
                    
                    result = await response.json()
                    
                    if result.get('errorId', 0) > 0:
                        raise CaptchaApiException(f"Помилка API Anti-Captcha: {result.get('errorDescription', 'Невідома помилка')}")
                    
                    return result
        except aiohttp.ClientError as e:
            raise CaptchaApiException(f"Помилка з'єднання з Anti-Captcha: {str(e)}")
    
    async def _wait_for_result(self, task_id: int) -> Dict[str, Any]:
        """
        Очікування результату розпізнавання CAPTCHA.
        
        :param task_id: ID завдання.
        :return: Результат розпізнавання CAPTCHA.
        """
        start_time = time.time()
        
        while time.time() - start_time < self.max_wait_time:
            await asyncio.sleep(self.check_interval)
            
            try:
                data = {
                    'taskId': task_id
                }
                
                result = await self._request('getTaskResult', data)
                
                if result['status'] == 'processing':
                    continue
                
                if result['status'] == 'ready':
                    return result
                
                raise CaptchaSolveException(f"Помилка при розпізнаванні CAPTCHA: {result.get('errorDescription', 'Невідома помилка')}")
            except CaptchaApiException as e:
                logger.error(f"Помилка при перевірці статусу CAPTCHA: {str(e)}")
                # Продовжуємо очікування у випадку помилки API
        
        raise CaptchaTimeoutException(f"Таймаут при очікуванні результату CAPTCHA")
    
    async def solve_image_captcha(self, image_data: Union[str, bytes]) -> str:
        """
        Розпізнати CAPTCHA з зображення.
        
        :param image_data: Дані зображення у вигляді шляху до файлу, URL або байтів.
        :return: Розпізнаний текст CAPTCHA.
        """
        # Перетворюємо дані зображення в Base64
        if isinstance(image_data, str):
            if image_data.startswith('http'):
                # Завантажуємо зображення за URL
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(image_data) as response:
                            if response.status != 200:
                                raise CaptchaSolveException(f"Помилка при завантаженні зображення: {response.status}")
                            image_bytes = await response.read()
                except Exception as e:
                    raise CaptchaSolveException(f"Помилка при завантаженні зображення: {str(e)}")
            else:
                # Читаємо файл з диску
                try:
                    with open(image_data, 'rb') as f:
                        image_bytes = f.read()
                except Exception as e:
                    raise CaptchaSolveException(f"Помилка при читанні файлу зображення: {str(e)}")
        else:
            # Використовуємо байти як є
            image_bytes = image_data
        
        # Кодуємо в Base64
        base64_image = base64.b64encode(image_bytes).decode('utf-8')
        
        try:
            # Формуємо завдання
            data = {
                'task': {
                    'type': 'ImageToTextTask',
                    'body': base64_image,
                    'phrase': False,
                    'case': False,
                    'numeric': 0,
                    'math': False,
                    'minLength': 0,
                    'maxLength': 0
                }
            }
            
            # Відправляємо завдання
            result = await self._request('createTask', data)
            task_id = result['taskId']
            
            # Очікуємо результат
            task_result = await self._wait_for_result(task_id)
            
            return task_result['solution']['text']
        except Exception as e:
            raise CaptchaSolveException(f"Помилка при розпізнаванні CAPTCHA: {str(e)}")
    
    async def solve_recaptcha(self, site_key: str, page_url: str) -> str:
        """
        Розпізнати reCAPTCHA.
        
        :param site_key: Ключ сайту для reCAPTCHA.
        :param page_url: URL сторінки, на якій розташована CAPTCHA.
        :return: Токен reCAPTCHA.
        """
        try:
            # Формуємо завдання
            data = {
                'task': {
                    'type': 'RecaptchaV2TaskProxyless',
                    'websiteURL': page_url,
                    'websiteKey': site_key
                }
            }
            
            # Відправляємо завдання
            result = await self._request('createTask', data)
            task_id = result['taskId']
            
            # Очікуємо результат
            task_result = await self._wait_for_result(task_id)
            
            return task_result['solution']['gRecaptchaResponse']
        except Exception as e:
            raise CaptchaSolveException(f"Помилка при розпізнаванні reCAPTCHA: {str(e)}")
    
    async def solve_hcaptcha(self, site_key: str, page_url: str) -> str:
        """
        Розпізнати hCaptcha.
        
        :param site_key: Ключ сайту для hCaptcha.
        :param page_url: URL сторінки, на якій розташована CAPTCHA.
        :return: Токен hCaptcha.
        """
        try:
            # Формуємо завдання
            data = {
                'task': {
                    'type': 'HCaptchaTaskProxyless',
                    'websiteURL': page_url,
                    'websiteKey': site_key
                }
            }
            
            # Відправляємо завдання
            result = await self._request('createTask', data)
            task_id = result['taskId']
            
            # Очікуємо результат
            task_result = await self._wait_for_result(task_id)
            
            return task_result['solution']['gRecaptchaResponse']
        except Exception as e:
            raise CaptchaSolveException(f"Помилка при розпізнаванні hCaptcha: {str(e)}")


class CaptchaSolverFactory:
    """Фабрика для створення розпізнавачів CAPTCHA."""
    
    @staticmethod
    def create_solver(service: str, api_key: str) -> CaptchaSolverBase:
        """
        Створити екземпляр розпізнавача CAPTCHA.
        
        :param service: Назва сервісу ('2captcha' або 'anti-captcha').
        :param api_key: API ключ для сервісу.
        :return: Екземпляр розпізнавача CAPTCHA.
        """
        if service.lower() == '2captcha':
            return TwoCaptchaSolver(api_key)
        elif service.lower() == 'anti-captcha':
            return AntiCaptchaSolver(api_key)
        else:
            raise ValueError(f"Непідтримуваний сервіс розпізнавання CAPTCHA: {service}")


class CaptchaDetector:
    """Клас для виявлення CAPTCHA на сторінці."""
    
    @staticmethod
    def detect_captcha_type(html: str) -> Optional[Tuple[str, Dict[str, str]]]:
        """
        Виявити тип CAPTCHA на сторінці.
        
        :param html: HTML код сторінки.
        :return: Кортеж з типом CAPTCHA і параметрами або None, якщо CAPTCHA не виявлено.
        """
        # Перевірка на наявність reCAPTCHA
        recaptcha_match = re.search(r'data-sitekey="([^"]+)"', html)
        if recaptcha_match:
            site_key = recaptcha_match.group(1)
            return 'recaptcha', {'site_key': site_key}
        
        # Перевірка на наявність hCaptcha
        hcaptcha_match = re.search(r'data-sitekey="([^"]+)".*?hcaptcha', html)
        if hcaptcha_match:
            site_key = hcaptcha_match.group(1)
            return 'hcaptcha', {'site_key': site_key}
        
        # Перевірка на наявність звичайної CAPTCHA (зображення)
        image_captcha_match = re.search(r'<img[^>]+captcha[^>]+src="([^"]+)"', html, re.IGNORECASE)
        if image_captcha_match:
            image_url = image_captcha_match.group(1)
            return 'image', {'image_url': image_url}
        
        return None 