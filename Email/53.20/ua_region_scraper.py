import requests
from bs4 import BeautifulSoup
import csv
import time
import random
import logging
import os
import datetime
import re
from urllib.parse import urljoin
import signal
import sys
import atexit

# Налаштування логування
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("scraping.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger()

class UARegionScraper:
    def __init__(self, kved=None):
        self.kved = kved
        self.base_url = f"https://www.ua-region.com.ua/kved/{kved}" if kved else "https://www.ua-region.com.ua/kved/53.20"
        self.output_file = f"companies_{kved.replace('.', '_')}.csv" if kved else "companies_53_20.csv"
        self.temp_folder = f"temp_data_{kved.replace('.', '_')}" if kved else "temp_data"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'uk-UA,uk;q=0.9,en-US;q=0.8,en;q=0.7',
            'Referer': 'https://www.ua-region.com.ua/',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Cache-Control': 'max-age=0',
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        
        # Забезпечимо створення папки для тимчасових файлів
        if not os.path.exists(self.temp_folder):
            os.makedirs(self.temp_folder)
            
        # Лічильники
        self.total_companies = None  # Буде встановлено після визначення кількості компаній
        self.companies_processed = 0
        self.start_time = None
        self.consecutive_failures = 0  # Лічильник послідовних невдач
        
        # Реєстрація обробників для коректного завершення
        atexit.register(self.cleanup)
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)
    
    def signal_handler(self, sig, frame):
        """Обробник сигналів для коректного завершення"""
        logger.info(f"Отримано сигнал {sig}. Виконую коректне завершення...")
        self.cleanup()
        sys.exit(0)
    
    def cleanup(self):
        """Функція для коректного завершення роботи скрапера"""
        if hasattr(self, 'companies_processed') and self.companies_processed > 0:
            logger.info(f"Виконую збереження проміжних результатів перед завершенням...")
            try:
                self.merge_results()
                logger.info(f"Проміжні результати успішно збережено у файл {self.output_file}")
                
                # Виведення статистики
                if self.start_time:
                    total_time = time.time() - self.start_time
                    hours, remainder = divmod(total_time, 3600)
                    minutes, seconds = divmod(remainder, 60)
                    
                    logger.info(f"Загальний час роботи: {int(hours)}г {int(minutes)}хв {int(seconds)}с")
                    logger.info(f"Оброблено {self.companies_processed} компаній")
            except Exception as e:
                logger.error(f"Помилка при збереженні результатів: {str(e)}")
    
    def human_like_delay(self):
        """Затримка, що імітує людську поведінку"""
        # Основна затримка - від 5 до 10 секунд
        delay = random.uniform(5, 10)
        
        # З шансом 20% збільшуємо затримку (пауза "на перекур" чи інші людські фактори)
        if random.random() < 0.2:
            delay += random.uniform(15, 25)
            
        # З шансом 1% робимо велику паузу (ніби людина відійшла)
        if random.random() < 0.1:
            delay += random.uniform(60, 120)
            logger.info(f"Довга пауза на {delay:.2f} секунд...")
            
        return delay
    
    def get_page(self, url, retry_count=5):
        """Отримання сторінки з обробкою помилок"""
        for attempt in range(retry_count):
            try:
                # Затримка перед запитом
                delay = self.human_like_delay()
                time.sleep(delay)
                
                logger.info(f"Спроба {attempt+1}: Запит до {url} (затримка {delay:.2f}с)")
                response = self.session.get(url, timeout=30)
                
                if response.status_code == 200:
                    logger.info(f"Успішно отримано сторінку {url}")
                    self.consecutive_failures = 0  # Скидаємо лічильник невдач при успіху
                    return response.text
                elif response.status_code == 403 or response.status_code == 429:
                    wait_time = random.uniform(180, 300)  # 3-5 хвилин
                    logger.warning(f"Отримано код {response.status_code}. Чекаємо {wait_time:.0f} секунд перед повторною спробою...")
                    time.sleep(wait_time)
                    # Оновлюємо User-Agent
                    self.rotate_user_agent()
                elif response.status_code == 404:
                    # Якщо отримали 404 помилку двічі, завершуємо роботу
                    if attempt >= 1:  # Це вже друга спроба
                        logger.error(f"Отримано код 404 двічі для {url}. Сторінка не існує. Завершення роботи...")
                        self.cleanup()
                        return "NEXT_KVED"  # Замість sys.exit(0) повертаємо сигнал для переходу до наступного КВЕДу
                    else:
                        logger.warning(f"Отримано код 404 для {url}. Спробуємо ще раз...")
                        time.sleep(random.uniform(30, 60))
                else:
                    logger.error(f"Помилка {response.status_code} при запиті {url}")
                    time.sleep(random.uniform(30, 60))
            except Exception as e:
                logger.error(f"Виняток при запиті {url}: {str(e)}")
                time.sleep(random.uniform(30, 60))
        
        logger.critical(f"Не вдалося отримати сторінку {url} після {retry_count} спроб")
        self.consecutive_failures += 1  # Збільшуємо лічильник невдач
        
        # Перевіряємо, чи досягнуто ліміту послідовних невдач
        if self.consecutive_failures >= 2:
            logger.critical(f"Досягнуто ліміту послідовних невдач (2). Переходимо до наступного КВЕДу...")
            return "NEXT_KVED"
        
        if self.consecutive_failures >= 4:
            logger.critical(f"Досягнуто ліміту послідовних невдач (4). Завершення роботи...")
            self.cleanup()
            sys.exit(1)
            
        return None
    
    def rotate_user_agent(self):
        """Зміна User-Agent для імітації різних браузерів"""
        user_agents = [
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
        new_agent = random.choice(user_agents)
        self.headers['User-Agent'] = new_agent
        self.session.headers.update(self.headers)
        logger.info(f"User-Agent змінено на: {new_agent}")
    
    def get_total_companies(self):
        """Визначення загальної кількості компаній"""
        html = self.get_page(self.base_url)
        if not html:
            logger.warning("Не вдалося отримати головну сторінку для визначення кількості компаній")
            return None
        elif html == "NEXT_KVED":
            return "NEXT_KVED"
            
        soup = BeautifulSoup(html, 'html.parser')
        
        # Спроба 1: Пошук прямого вказання кількості компаній
        try:
            # Шукаємо елемент, який містить інформацію про кількість компаній
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
        
        # Спроба 2: Визначення за кількістю сторінок
        total_pages = self.get_total_pages()
        if total_pages and total_pages != "NEXT_KVED":
            # Оцінюємо кількість компаній на основі кількості сторінок
            # Припускаємо, що на кожній сторінці приблизно 20 компаній
            estimated_companies = total_pages * 20
            logger.info(f"Оцінка кількості компаній на основі {total_pages} сторінок: {estimated_companies}")
            return estimated_companies
        
        # Спроба 3: Використовуємо значення за замовчуванням
        default_value = 20000  # Розумне значення за замовчуванням
        logger.warning(f"Не вдалося визначити кількість компаній. Використовуємо значення за замовчуванням: {default_value}")
        return default_value
    
    def get_total_pages(self):
        """Визначення загальної кількості сторінок"""
        html = self.get_page(f"{self.base_url}?start_page=1")
        if not html:
            logger.warning("Не вдалося отримати сторінку для визначення кількості сторінок")
            return 0
        elif html == "NEXT_KVED":
            return "NEXT_KVED"
            
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
        
        # Якщо не вдалося визначити кількість сторінок через пагінацію
        logger.warning("Не вдалося визначити кількість сторінок через пагінацію")
        
        # Спробуємо знайти інформацію про кількість компаній і розрахувати кількість сторінок
        if self.total_companies and self.total_companies != "NEXT_KVED":
            pages = (self.total_companies + 19) // 20  # 20 компаній на сторінку
            logger.info(f"Розраховано {pages} сторінок на основі {self.total_companies} компаній")
            return pages
        
        # Якщо все невдало, повертаємо розумне значення за замовчуванням
        default_pages = 2000 
        logger.warning(f"Використовуємо значення за замовчуванням: {default_pages} сторінок")
        return default_pages
    
    def process_page(self, page_num):
        """Обробка однієї сторінки результатів"""
        url = f"{self.base_url}?start_page={page_num}"
        logger.info(f"Обробка сторінки {page_num}")
        
        html = self.get_page(url)
        if not html:
            logger.error(f"Не вдалося отримати сторінку {page_num}")
            return []
        elif html == "NEXT_KVED":
            return "NEXT_KVED"
        
        soup = BeautifulSoup(html, 'html.parser')
        companies_list = soup.find_all('div', class_='row p-3 p-md-4')
        
        logger.info(f"Знайдено елементів компаній: {len(companies_list)}")
        
        results = []
        for company in companies_list:
            info = self.extract_company_info(company)
            if info['Назва']:  # Додаємо тільки компанії з назвою
                results.append(info)
                self.companies_processed += 1
                self.log_progress()
        
        logger.info(f"Зібрано {len(results)} компаній зі сторінки {page_num}")
        
        # Зберігаємо результати, якщо знайшли хоч щось
        if results:
            self.save_temp_results(page_num, results)
        
        return results
    
    def extract_company_info(self, company_element):
        """Витягнення інформації про компанію з HTML-елемента"""
        info = {'Назва': '', 'Адреса': '', 'Телефон': '', 'Email': ''}
        
        # Назва компанії
        title_div = company_element.find('div', class_='cart-company-lg__title')
        if title_div:
            name_link = title_div.find('a')
            if name_link:
                info['Назва'] = name_link.text.strip()
                logger.debug(f"Знайдено назву: {info['Назва']}")
        
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
                    info['Адреса'] = span.text.strip()
                    logger.debug(f"Знайдено адресу: {info['Адреса']}")
                    
                elif 'phone' in icon_ref:  # Телефон
                    phone_links = span.find_all('a')
                    phones = [link.text.strip() for link in phone_links]
                    info['Телефон'] = ', '.join(phones)
                    logger.debug(f"Знайдено телефони: {info['Телефон']}")
                    
                elif 'email' in icon_ref:  # Email
                    email_link = span.find('a')
                    if email_link:
                        info['Email'] = email_link.text.strip()
                        logger.debug(f"Знайдено email: {info['Email']}")
        
        # Додайте перевірку, щоб бачити які компанії знайдено
        if info['Назва']:
            logger.info(f"Знайдено компанію: {info['Назва']}")
        
        return info
    
    def log_progress(self):
        """Виведення інформації про прогрес"""
        if not self.start_time or not self.total_companies or self.total_companies == "NEXT_KVED":
            return
            
        progress = (self.companies_processed / self.total_companies) * 100
        elapsed_time = time.time() - self.start_time
        if self.companies_processed > 0:
            time_per_company = elapsed_time / self.companies_processed
            remaining_companies = self.total_companies - self.companies_processed
            estimated_time_left = remaining_companies * time_per_company
            
            # Конвертуємо в години, хвилини, секунди
            hours, remainder = divmod(estimated_time_left, 3600)
            minutes, seconds = divmod(remainder, 60)
            
            # Логуємо кожні 20 компаній
            if self.companies_processed % 20 == 0:
                logger.info(f"Прогрес: {self.companies_processed}/{self.total_companies} " +
                          f"({progress:.2f}%). Залишилось приблизно: " +
                          f"{int(hours)}г {int(minutes)}хв {int(seconds)}с")
    
    def save_temp_results(self, page_num, results):
        """Збереження проміжних результатів"""
        temp_file = os.path.join(self.temp_folder, f"page_{page_num}.csv")
        with open(temp_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['Назва', 'Адреса', 'Телефон', 'Email'])
            writer.writeheader()
            writer.writerows(results)
        logger.info(f"Збережено проміжні результати для сторінки {page_num}")
    
    def check_resume_point(self):
        """Перевірка наявності точки відновлення"""
        if not os.path.exists(self.temp_folder):
            return 1
            
        processed_pages = []
        for filename in os.listdir(self.temp_folder):
            if filename.startswith('page_') and filename.endswith('.csv'):
                try:
                    page_num = int(filename.replace('page_', '').replace('.csv', ''))
                    processed_pages.append(page_num)
                except ValueError:
                    continue
        
        if processed_pages:
            return max(processed_pages) + 1
        return 1
    
    def merge_results(self):
        """Об'єднання всіх проміжних результатів в один файл"""
        logger.info("Об'єднання результатів...")
        all_results = []
        
        for filename in sorted(os.listdir(self.temp_folder)):
            if filename.startswith('page_') and filename.endswith('.csv'):
                file_path = os.path.join(self.temp_folder, filename)
                with open(file_path, 'r', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        all_results.append(row)
        
        with open(self.output_file, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['Назва', 'Адреса', 'Телефон', 'Email'])
            writer.writeheader()
            writer.writerows(all_results)
        
        logger.info(f"Всі результати збережено у файл {self.output_file}")
        logger.info(f"Всього зібрано {len(all_results)} компаній")
    
    def run(self):
        """Основний метод для запуску скрапінгу"""
        logger.info(f"Початок збору даних для КВЕД {self.kved}...")
        self.start_time = time.time()
        
        # Спочатку визначаємо загальну кількість компаній
        self.total_companies = self.get_total_companies()
        if self.total_companies == "NEXT_KVED":
            logger.warning(f"Переходимо до наступного КВЕДу після невдалих спроб для {self.kved}")
            return "NEXT_KVED"
            
        logger.info(f"Загальна кількість компаній для збору: {self.total_companies}")
        
        # Визначаємо загальну кількість сторінок
        total_pages = self.get_total_pages()
        if total_pages == "NEXT_KVED":
            logger.warning(f"Переходимо до наступного КВЕДу після невдалих спроб для {self.kved}")
            return "NEXT_KVED"
            
        if total_pages == 0:
            logger.error("Не вдалося визначити кількість сторінок. Перевірте доступність сайту.")
            return
        
        logger.info(f"Знайдено {total_pages} сторінок для обробки")
        
        # Перевіряємо, чи є точка відновлення
        start_page = self.check_resume_point()
        if start_page > 1:
            logger.info(f"Відновлення роботи з сторінки {start_page}")
        
        # Обробляємо сторінки
        for page_num in range(start_page, total_pages + 1):
            logger.info(f"Обробка сторінки {page_num} з {total_pages}")
            
            try:
                results = self.process_page(page_num)
                if results == "NEXT_KVED":
                    logger.warning(f"Переходимо до наступного КВЕДу після невдалих спроб для {self.kved}")
                    return "NEXT_KVED"
                    
                if results:
                    self.save_temp_results(page_num, results)
                
                # З шансом 5% робимо довгу паузу для імітації перерви в роботі
                if random.random() < 0.05:
                    pause_time = random.uniform(300, 600)  # 5-10 хвилин
                    logger.info(f"Роблю велику паузу на {pause_time:.0f} секунд для імітації перерви...")
                    time.sleep(pause_time)
                    # Оновлюємо User-Agent після паузи
                    self.rotate_user_agent()
            except Exception as e:
                logger.error(f"Помилка при обробці сторінки {page_num}: {str(e)}")
                # Робимо паузу перед продовженням
                time.sleep(random.uniform(60, 120))
        
        # Об'єднуємо результати з усіх сторінок
        self.merge_results()
        
        # Обчислюємо загальний час виконання
        total_time = time.time() - self.start_time
        hours, remainder = divmod(total_time, 3600)
        minutes, seconds = divmod(remainder, 60)
        
        logger.info(f"Збір даних завершено за {int(hours)}г {int(minutes)}хв {int(seconds)}с")
        logger.info(f"Результати збережено у файл {self.output_file}")

def is_kved_downloaded(kved):
    """Перевірка чи вже завантажено дані для КВЕДу"""
    output_file = f"companies_{kved.replace('.', '_')}.csv"
    
    # Перевіряємо наявність файлу з результатами
    if os.path.exists(output_file):
        try:
            # Перевіряємо, чи файл не порожній і містить дані
            with open(output_file, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                header = next(reader, None)  # Пропускаємо заголовок
                first_row = next(reader, None)  # Перевіряємо наявність хоча б одного рядка даних
                
                if header and first_row:
                    logger.info(f"КВЕД {kved} вже завантажено (знайдено файл з даними)")
                    return True
        except Exception as e:
            logger.warning(f"Помилка при перевірці файлу для КВЕД {kved}: {str(e)}")
    
    # Перевіряємо наявність тимчасової папки з даними
    temp_folder = f"temp_data_{kved.replace('.', '_')}"
    if os.path.exists(temp_folder) and os.listdir(temp_folder):
        logger.info(f"Знайдено тимчасові дані для КВЕД {kved}, потрібно продовжити завантаження")
        return False
    
    logger.info(f"КВЕД {kved} ще не завантажено")
    return False

def scrape_all_kveds():
    """Функція для запуску скрапінгу для всіх вказаних КВЕДів"""
    kveds = [
        # Освіта
        "85.10", "85.20", "85.31", "85.32", "85.42", "85.59",
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
        # Сільське господарство
        "01.50",
        # Видавництво
        "58.11", "58.12", "58.19", "58.13", "58.14",
        # Роздрібна торгівля
        "47.61", "47.78", "47.62", "47.11",
    ]
    
    logger.info(f"Починаю збір даних для {len(kveds)} КВЕДів")
    
    consecutive_failures = 0
    total_kveds = len(kveds)
    
    # Створюємо список для відстеження завантажених КВЕДів
    downloaded_kveds = []
    
    # Перевіряємо, які КВЕДи вже завантажено
    for kved in kveds:
        if is_kved_downloaded(kved):
            downloaded_kveds.append(kved)
            logger.info(f"КВЕД {kved} вже завантажено")
    
    logger.info(f"Завантажено {len(downloaded_kveds)} з {total_kveds} КВЕДів")
    
    # Продовжуємо роботу, поки не будуть завантажені всі КВЕДи
    while len(downloaded_kveds) < total_kveds:
        for kved in kveds:
            # Пропускаємо вже завантажені КВЕДи
            if kved in downloaded_kveds:
                continue
                
            logger.info(f"Обробка КВЕД {kved} ({len(downloaded_kveds) + 1}/{total_kveds})")
            
            try:
                scraper = UARegionScraper(kved=kved)
                result = scraper.run()
                
                if result == "NEXT_KVED":
                    consecutive_failures += 1
                    logger.warning(f"Невдала спроба для КВЕД {kved}. Послідовних невдач: {consecutive_failures}")
                    
                    if consecutive_failures >= 4:
                        logger.critical(f"Досягнуто ліміту послідовних невдач для КВЕДів (4). Завершення роботи...")
                        return
                else:
                    consecutive_failures = 0  # Скидаємо лічильник при успіху
                    logger.info(f"Завершено обробку КВЕД {kved}")
                    downloaded_kveds.append(kved)
                
                # Перевіряємо ще раз, чи було успішно завантажено
                if is_kved_downloaded(kved) and kved not in downloaded_kveds:
                    downloaded_kveds.append(kved)
                    logger.info(f"КВЕД {kved} підтверджено як завантажений")
                
                # Пауза між обробкою різних КВЕДів
                pause_time = random.uniform(60, 180)  # 1-3 хвилини
                logger.info(f"Пауза між КВЕДами: {pause_time:.0f} секунд")
                time.sleep(pause_time)
            except Exception as e:
                logger.error(f"Помилка при обробці КВЕД {kved}: {str(e)}")
                consecutive_failures += 1
                
                if consecutive_failures >= 4:
                    logger.critical(f"Досягнуто ліміту послідовних невдач для КВЕДів (4). Завершення роботи...")
                    return
        
        # Якщо пройшли всі КВЕДи, але ще не всі завантажені, робимо довгу паузу
        if len(downloaded_kveds) < total_kveds:
            remaining = total_kveds - len(downloaded_kveds)
            logger.info(f"Завершено цикл, але ще залишилось {remaining} КВЕДів для завантаження")
            logger.info("Роблю довгу паузу перед повторною спробою...")
            time.sleep(random.uniform(300, 600))  # 5-10 хвилин паузи
    
    logger.info("Збір даних для всіх КВЕДів завершено")

if __name__ == "__main__":
    try:
        # Запускаємо скрапінг для всіх КВЕДів
        scrape_all_kveds()
    except KeyboardInterrupt:
        logger.info("Скрипт зупинено користувачем. Проміжні результати збережено.")
    except Exception as e:
        logger.critical(f"Критична помилка: {str(e)}")