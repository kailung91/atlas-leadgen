"""
Парсер HTML для витягнення даних компаній.
"""
import logging
import re
from typing import List, Dict, Any, Optional, Tuple
from bs4 import BeautifulSoup
from urllib.parse import urljoin

from models import CompanyData
from exceptions import ParseException

logger = logging.getLogger(__name__)


class HtmlParser:
    """Клас для парсингу HTML та витягнення даних компаній."""
    
    @staticmethod
    def extract_company_info(company_element) -> CompanyData:
        """Витягнення інформації про компанію з HTML-елемента."""
        try:
            name = ''
            address = ''
            phone = ''
            email = ''
            
            # Назва компанії
            title_div = company_element.find('div', class_='cart-company-lg__title')
            if title_div:
                name_link = title_div.find('a')
                if name_link:
                    name = name_link.text.strip()
                    logger.debug(f"Знайдено назву: {name}")
            
            # Список елементів з інформацією
            info_list = company_element.find('ul', class_='cart-company-lg__list')
            if info_list:
                list_items = info_list.find_all('li')
                
                for item in list_items:
                    svg = item.find('svg')
                    if not svg or not svg.find('use'):
                        continue
                        
                    use_tag = svg.find('use')
                    icon_ref = use_tag.get('xlink:href', '')
                    
                    # Отримуємо span з даними
                    span = item.find('span', class_='cart-company-lg__list-link')
                    if not span:
                        continue
                        
                    # Визначаємо тип інформації за іконкою
                    if 'pin' in icon_ref:  # Адреса
                        address = span.text.strip()
                        logger.debug(f"Знайдено адресу: {address}")
                        
                    elif 'phone' in icon_ref:  # Телефон
                        phone_links = span.find_all('a')
                        phones = [link.text.strip() for link in phone_links]
                        phone = ', '.join(phones)
                        logger.debug(f"Знайдено телефони: {phone}")
                        
                    elif 'email' in icon_ref:  # Email
                        email_link = span.find('a')
                        if email_link:
                            email = email_link.text.strip()
                            logger.debug(f"Знайдено email: {email}")
            
            return CompanyData(name=name, address=address, phone=phone, email=email)
        
        except Exception as e:
            logger.error(f"Помилка при витяганні інформації про компанію: {str(e)}")
            return CompanyData(name="")  # Повертаємо порожній об'єкт у випадку помилки
    
    @staticmethod
    def parse_companies_from_page(html: str) -> List[CompanyData]:
        """Парсинг всіх компаній на сторінці."""
        soup = BeautifulSoup(html, 'html.parser')
        companies_list = soup.find_all('div', class_='row p-3 p-md-4')
        
        logger.info(f"Знайдено елементів компаній: {len(companies_list)}")
        
        results = []
        for company in companies_list:
            info = HtmlParser.extract_company_info(company)
            if info.name:  # Додаємо тільки компанії з назвою
                results.append(info)
        
        logger.info(f"Успішно опрацьовано {len(results)} компаній")
        return results
    
    @staticmethod
    def get_total_companies(html: str) -> Optional[int]:
        """Визначення загальної кількості компаній з HTML."""
        soup = BeautifulSoup(html, 'html.parser')
        
        try:
            # Спроба 1: Пошук прямого вказання кількості компаній
            info_text = soup.find('div', class_='search-result__info')
            if info_text:
                text = info_text.text.strip()
                # Шукаємо числа в тексті
                numbers = re.findall(r'\d+', text)
                if numbers:
                    total = int(numbers[0])
                    logger.info(f"Знайдено загальну кількість компаній: {total}")
                    return total
        except Exception as e:
            logger.warning(f"Помилка при спробі знайти кількість компаній: {str(e)}")
        
        return None
    
    @staticmethod
    def get_total_pages(html: str) -> Optional[int]:
        """Визначення загальної кількості сторінок з HTML."""
        soup = BeautifulSoup(html, 'html.parser')
        
        # Пошук пагінації
        pagination_div = soup.find('div', class_='pagination')
        if pagination_div:
            links = pagination_div.find_all('a')
            page_numbers = []
            for link in links:
                try:
                    # Перевіряємо текст посилання
                    link_text = link.text.strip()
                    # Якщо це число, додаємо його
                    if link_text.isdigit():
                        page_num = int(link_text)
                        page_numbers.append(page_num)
                    # Якщо це "Остання", шукаємо номер сторінки в URL
                    elif "Остання" in link_text or "остання" in link_text.lower():
                        href = link.get('href', '')
                        page_match = re.search(r'start_page=(\d+)', href)
                        if page_match:
                            last_page = int(page_match.group(1))
                            page_numbers.append(last_page)
                except ValueError:
                    continue
            
            if page_numbers:
                max_page = max(page_numbers)
                logger.info(f"Знайдено {max_page} сторінок")
                return max_page
        
        return None
    
    @staticmethod
    def parse_honeypot_elements(html: str) -> bool:
        """
        Перевірка на наявність honeypot елементів, які можуть вказувати на те,
        що сайт намагається виявити скрапери.
        """
        soup = BeautifulSoup(html, 'html.parser')
        
        # Перевірка на приховані поля форм (часто використовуються як honeypot)
        hidden_inputs = soup.find_all('input', {'type': 'hidden'})
        suspicious_inputs = [inp for inp in hidden_inputs if 'bot' in inp.get('name', '').lower() 
                           or 'spam' in inp.get('name', '').lower()
                           or 'honey' in inp.get('name', '').lower()]
        
        if suspicious_inputs:
            logger.warning(f"Виявлено потенційні honeypot елементи: {len(suspicious_inputs)}")
            return True
        
        # Перевірка на невидимі елементи через CSS
        invisible_elements = soup.find_all(style=re.compile(r'display:\s*none|visibility:\s*hidden|opacity:\s*0'))
        if len(invisible_elements) > 5:  # Якщо більше 5 невидимих елементів, це підозріло
            logger.warning(f"Виявлено багато невидимих елементів: {len(invisible_elements)}")
            return True
        
        # Перевірка на наявність Cloudflare або інших антибот систем
        cloudflare_elements = soup.find_all(text=re.compile(r'cloudflare|challenge|captcha|robot|human verification'))
        if cloudflare_elements:
            logger.warning("Виявлено елементи Cloudflare або CAPTCHA")
            return True
        
        return False
    
    @staticmethod
    def check_captcha(html: str) -> bool:
        """Перевірка наявності CAPTCHA на сторінці."""
        soup = BeautifulSoup(html, 'html.parser')
        
        # Пошук за ключовими словами в тексті
        captcha_texts = [
            'captcha', 'recaptcha', 'g-recaptcha', 'hcaptcha', 'перевірка',
            'я не робот', 'підтвердити', 'verification', 'verify'
        ]
        
        for text in captcha_texts:
            elements = soup.find_all(text=re.compile(text, re.IGNORECASE))
            if elements:
                logger.warning(f"Виявлено CAPTCHA: {text}")
                return True
        
        # Пошук зображень CAPTCHA
        img_elements = soup.find_all('img', {'src': re.compile(r'captcha|verification|security', re.IGNORECASE)})
        if img_elements:
            logger.warning("Виявлено зображення CAPTCHA")
            return True
        
        # Пошук формування CAPTCHA через iframe (reCAPTCHA)
        iframe_elements = soup.find_all('iframe', {'src': re.compile(r'recaptcha|captcha', re.IGNORECASE)})
        if iframe_elements:
            logger.warning("Виявлено iframe CAPTCHA")
            return True
        
        # Пошук скриптів CAPTCHA
        script_elements = soup.find_all('script', {'src': re.compile(r'recaptcha|captcha|hcaptcha', re.IGNORECASE)})
        if script_elements:
            logger.warning("Виявлено скрипти CAPTCHA")
            return True
        
        return False 