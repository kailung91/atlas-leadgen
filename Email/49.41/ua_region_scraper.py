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
    def __init__(self):
        self.base_url = "https://www.ua-region.com.ua/kved/49.41"
        self.output_file = "companies_49_41.csv"
        self.temp_folder = "temp_data"
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
        self.total_companies = 11065
        self.companies_processed = 0
        self.start_time = None
    
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
                    return response.text
                elif response.status_code == 403 or response.status_code == 429:
                    wait_time = random.uniform(180, 300)  # 3-5 хвилин
                    logger.warning(f"Отримано код {response.status_code}. Чекаємо {wait_time:.0f} секунд перед повторною спробою...")
                    time.sleep(wait_time)
                    # Оновлюємо User-Agent
                    self.rotate_user_agent()
                else:
                    logger.error(f"Помилка {response.status_code} при запиті {url}")
                    time.sleep(random.uniform(30, 60))
            except Exception as e:
                logger.error(f"Виняток при запиті {url}: {str(e)}")
                time.sleep(random.uniform(30, 60))
        
        logger.critical(f"Не вдалося отримати сторінку {url} після {retry_count} спроб")
        return None
    
    def rotate_user_agent(self):
        """Зміна User-Agent для імітації різних браузерів"""
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15',
            'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Edge/120.0.0.0'
        ]
        new_agent = random.choice(user_agents)
        self.headers['User-Agent'] = new_agent
        self.session.headers.update(self.headers)
        logger.info(f"User-Agent змінено на: {new_agent}")
    
    def get_total_pages(self):
        """Визначення загальної кількості сторінок"""
        html = self.get_page(f"{self.base_url}?start_page=1")
        if not html:
            return 0
            
        soup = BeautifulSoup(html, 'html.parser')
        
        # Пошук пагінації
        pagination_div = soup.find('div', class_='pagination')
        if pagination_div:
            links = pagination_div.find_all('a')
            page_numbers = []
            for link in links:
                try:
                    page_num = int(link.text.strip())
                    page_numbers.append(page_num)
                except ValueError:
                    continue
            
            if page_numbers:
                return max(page_numbers)
        
        # Якщо не вдалося визначити, рахуємо на основі кількості компаній
        return (self.total_companies + 19) // 20  # 20 компаній на сторінку
    
    def process_page(self, page_num):
        """Обробка однієї сторінки результатів"""
        url = f"{self.base_url}?start_page={page_num}"
        logger.info(f"Обробка сторінки {page_num}")
        
        html = self.get_page(url)
        if not html:
            logger.error(f"Не вдалося отримати сторінку {page_num}")
            return []
        
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
        if not self.start_time:
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
        logger.info("Початок збору даних...")
        self.start_time = time.time()
        
        # Визначаємо загальну кількість сторінок
        total_pages = self.get_total_pages()
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

if __name__ == "__main__":
    try:
        scraper = UARegionScraper()
        scraper.run()
    except KeyboardInterrupt:
        logger.info("Скрипт зупинено користувачем. Проміжні результати збережено.")
    except Exception as e:
        logger.critical(f"Критична помилка: {str(e)}")