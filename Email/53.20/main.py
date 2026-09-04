"""
Точка входу для запуску скрапера.
"""
import argparse
import logging
import sys
import os
import asyncio
import traceback
from typing import List, Optional

from config import LOGGING_CONFIG, KVEDS, ensure_data_directory
from scraper import scrape_kved, scrape_all_kveds
from lock_manager import LockManager
from exceptions import LockException


def setup_logging():
    """Налаштування логування."""
    log_level = getattr(logging, LOGGING_CONFIG['level'])
    log_format = LOGGING_CONFIG['format']
    
    # Створюємо обробники
    handlers = []
    if 'file' in LOGGING_CONFIG['handlers']:
        file_handler = logging.FileHandler(LOGGING_CONFIG['file_path'])
        file_handler.setFormatter(logging.Formatter(log_format))
        handlers.append(file_handler)
    
    if 'console' in LOGGING_CONFIG['handlers']:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter(log_format))
        handlers.append(console_handler)
    
    # Налаштовуємо кореневий логер
    logging.basicConfig(
        level=log_level,
        format=log_format,
        handlers=handlers
    )


def parse_arguments():
    """Парсинг аргументів командного рядка."""
    parser = argparse.ArgumentParser(description='Скрапер компаній за КВЕДами з сайту UA-Region')
    
    # Вибір режиму роботи
    group = parser.add_mutually_exclusive_group()
    group.add_argument('-k', '--kved', type=str, help='Конкретний КВЕД для скрапінгу')
    group.add_argument('-a', '--all', action='store_true', help='Обробити всі КВЕДи з конфігурації')
    group.add_argument('-l', '--list', action='store_true', help='Список доступних КВЕДів')
    
    # Додаткові параметри
    parser.add_argument('-v', '--verbose', action='store_true', help='Детальне логування')
    parser.add_argument('-f', '--force', action='store_true', help='Примусово запустити, ігноруючи блокування')
    
    return parser.parse_args()


def print_kveds_list(kveds: List[str]):
    """Вивести список доступних КВЕДів."""
    print("Доступні КВЕДи для скрапінгу:")
    
    # Групуємо КВЕДи за категоріями
    categories = {
        "Освіта": ["85.10", "85.20", "85.31", "85.32", "85.40", "85.42", "85.59"],
        "Транспорт": ["49.41", "49.42", "53.20", "49.31", "49.39"],
        "Туризм": ["79.11", "55.10", "79.90"],
        "Музеї": ["91.02", "91.03"],
        "Нерухомість": ["41.10", "41.20", "68.10", "71.11", "68.31"],
        "Державне управління": ["84.11", "84.12"],
        "Видавництво": ["58.11", "58.12", "58.19", "58.13", "58.14"],
        "Роздрібна торгівля": ["47.61", "47.78", "47.62"],
        "Сільське господарство": ["01.1", "01.2", "01.3", "01.4", "01.5", "01.6", "01.7"]
    }
    
    for category, cat_kveds in categories.items():
        print(f"\n{category}:")
        for kved in cat_kveds:
            print(f"  {kved}")


def main():
    """Основна функція."""
    # Налаштовуємо логування
    setup_logging()
    logger = logging.getLogger(__name__)
    
    # Перевіряємо наявність директорії для даних
    ensure_data_directory()
    
    # Парсимо аргументи
    args = parse_arguments()
    
    # Встановлюємо рівень логування
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.debug("Встановлено детальний режим логування")
    
    try:
        # Показуємо список КВЕДів
        if args.list:
            print_kveds_list(KVEDS)
            return 0
        
        # Перевіряємо блокування, якщо не вказано --force
        if not args.force:
            lock_manager = LockManager()
            if lock_manager.check_lock():
                logger.error("Виявлено активне блокування. Можливо, скрапер вже запущений.")
                logger.error("Використайте параметр --force для примусового запуску.")
                return 1
        
        # Запускаємо скрапінг
        if args.kved:
            logger.info(f"Запуск скрапінгу для КВЕДу {args.kved}")
            if scrape_kved(args.kved):
                logger.info(f"Скрапінг КВЕДу {args.kved} успішно завершено")
                return 0
            else:
                logger.error(f"Скрапінг КВЕДу {args.kved} завершено з помилками")
                return 1
        elif args.all:
            logger.info("Запуск скрапінгу для всіх КВЕДів")
            scrape_all_kveds()
            logger.info("Скрапінг всіх КВЕДів завершено")
            return 0
        else:
            logger.error("Не вказано режим роботи. Використайте -k або -a")
            return 1
    
    except LockException as e:
        logger.error(f"Помилка блокування: {str(e)}")
        logger.error("Використайте параметр --force для примусового запуску.")
        return 1
    except KeyboardInterrupt:
        logger.info("Скрипт зупинено користувачем. Проміжні результати збережено.")
        return 0
    except Exception as e:
        logger.critical(f"Критична помилка: {str(e)}")
        logger.debug(traceback.format_exc())
        return 1


if __name__ == "__main__":
    sys.exit(main()) 