import os
import re
import json
import requests
import pytesseract
from io import BytesIO
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from PIL import Image
import shutil
from typing import List, Dict, Set, Optional, Union


class CompleteWebsiteScraper:
    def __init__(self, root_url: str, max_pages: int = 50, ocr_enabled: bool = True,
                 max_file_size: int = 10 * 1024 * 1024, download_documents: bool = False):
        """
        Инициализация парсера веб-сайтов

        Args:
            root_url: Начальный URL для парсинга
            max_pages: Максимальное количество страниц для обработки
            ocr_enabled: Включить распознавание текста с изображений
            max_file_size: Максимальный размер файлов для скачивания (в байтах)
            download_documents: Скачивать документы (PDF, DOCX и т.д.)
        """
        self.root_url = root_url
        self.visited_urls: Set[str] = set()
        self.data: List[Dict] = []
        self.max_pages = max_pages
        self.ocr_enabled = ocr_enabled
        self.max_file_size = max_file_size
        self.download_documents = download_documents

        # Настройка сессии requests
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })

        # Проверка и настройка Tesseract OCR
        if self.ocr_enabled:
            try:
                pytesseract.pytesseract.tesseract_cmd = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
                pytesseract.get_tesseract_version()
            except Exception as e:
                print(f"Ошибка инициализации Tesseract OCR: {e}")
                self.ocr_enabled = False

        # Создание папок для сохранения данных
        os.makedirs('downloaded_documents', exist_ok=True)
        os.makedirs('temp_images', exist_ok=True)

    def is_valid_url(self, url: str) -> bool:
        """Проверяет, принадлежит ли URL тому же домену, что и root_url"""
        parsed = urlparse(url)
        return bool(parsed.netloc) and parsed.netloc == urlparse(self.root_url).netloc

    def download_file(self, url: str, file_type: str) -> Optional[str]:
        """
        Скачивает файл и сохраняет его на диск

        Args:
            url: URL файла для скачивания
            file_type: Тип файла (расширение)

        Returns:
            Путь к сохраненному файлу или None при ошибке
        """
        try:
            response = self.session.get(url, stream=True, timeout=30)
            response.raise_for_status()

            filename = os.path.join('downloaded_documents',
                                    f"document_{len(self.visited_urls)}_{file_type}.{file_type}")

            with open(filename, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)

            return filename
        except Exception as e:
            print(f"Ошибка при скачивании файла {url}: {str(e)}")
            return None

    def extract_text_from_image(self, img_url: str) -> str:
        """
        Извлекает текст с изображения с помощью OCR

        Args:
            img_url: URL изображения

        Returns:
            Распознанный текст или сообщение об ошибке
        """
        if not self.ocr_enabled:
            return "OCR отключен"

        try:
            # Загрузка изображения
            response = self.session.get(img_url, stream=True, timeout=60)
            response.raise_for_status()

            # Проверка размера и типа
            if int(response.headers.get('content-length', 0)) > self.max_file_size:
                return "Изображение слишком большое"
            if 'image' not in response.headers.get('content-type', ''):
                return "URL не ведет на изображение"

            # Сохранение временного файла
            temp_img_path = os.path.join('temp_images', os.path.basename(img_url))
            with open(temp_img_path, 'wb') as f:
                response.raw.decode_content = True
                shutil.copyfileobj(response.raw, f)

            # Распознавание текста
            text = pytesseract.image_to_string(Image.open(temp_img_path), lang='rus')
            os.remove(temp_img_path)  # Удаление временного файла

            return self.clean_text(text) if text.strip() else "Не удалось распознать текст"

        except Exception as e:
            print(f"Ошибка обработки изображения {img_url}: {str(e)}")
            return "Ошибка обработки изображения"

    def clean_text(self, text: str) -> str:
        """Очищает текст от лишних символов и форматирования"""
        text = re.sub(r'[^\w\s.,:;!?()\-\n]', '', text)
        text = re.sub(r'\s+', ' ', text)
        text = re.sub(r'-\s+', '', text)
        return text.strip()

    def extract_metadata(self, soup: BeautifulSoup, url: str) -> Dict:
        """Извлекает метаданные страницы"""
        metadata = {
            'title': soup.title.string if soup.title else None,
            'description': None,
            'keywords': None,
            'og': {},
            'headers': {}
        }

        # Мета-описания
        if meta_desc := soup.find('meta', attrs={'name': 'description'}):
            metadata['description'] = meta_desc.get('content')
        if meta_keywords := soup.find('meta', attrs={'name': 'keywords'}):
            metadata['keywords'] = meta_keywords.get('content')

        # OpenGraph метаданные
        for meta in soup.find_all('meta', property=lambda x: x and x.startswith('og:')):
            metadata['og'][meta['property']] = meta['content']

        return metadata

    def extract_links(self, soup: BeautifulSoup, base_url: str) -> Dict[str, Set[str]]:
        """Извлекает все ссылки со страницы и классифицирует их"""
        links = {
            'internal': set(),
            'external': set(),
            'files': {
                'pdf': set(),
                'images': set(),
                'other': set()
            }
        }

        for a in soup.find_all('a', href=True):
            href = a['href']
            absolute_url = urljoin(base_url, href)

            if not self.is_valid_url(absolute_url):
                links['external'].add(absolute_url)
                continue

            # Классификация файлов
            if href.lower().endswith('.pdf'):
                links['files']['pdf'].add(absolute_url)
            elif any(href.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png', '.gif', '.bmp']):
                links['files']['images'].add(absolute_url)
            elif '.' in href.split('/')[-1]:
                links['files']['other'].add(absolute_url)
            else:
                links['internal'].add(absolute_url)

        return links

    def scrape_page(self, url: str) -> None:
        """Рекурсивно парсит страницу и все внутренние ссылки"""
        if url in self.visited_urls or len(self.visited_urls) >= self.max_pages:
            return

        print(f"Обработка: {url}")
        self.visited_urls.add(url)

        try:
            response = self.session.get(url, timeout=30)
            response.raise_for_status()

            if 'text/html' not in response.headers.get('content-type', ''):
                print(f"Пропуск не-HTML контента: {url}")
                return

            soup = BeautifulSoup(response.text, 'html.parser')

            # Удаление ненужных элементов
            for element in soup(['script', 'style', 'iframe', 'noscript']):
                element.decompose()

            # Извлечение основного текста
            main_text = '\n'.join(line for line in soup.get_text('\n', strip=True).split('\n') if line.strip())

            # Извлечение текста с изображений
            img_texts = []
            if self.ocr_enabled:
                for img in soup.find_all('img', src=True):
                    img_url = urljoin(url, img.get('src'))
                    if any(img_url.lower().endswith(ext) for ext in ['.jpg', '.jpeg', '.png']):
                        ocr_text = self.extract_text_from_image(img_url)
                        if ocr_text:
                            img_texts.append({
                                'url': img_url,
                                'alt_text': img.get('alt', ''),
                                'ocr_text': ocr_text
                            })

            # Извлечение метаданных и ссылок
            metadata = self.extract_metadata(soup, url)
            links = self.extract_links(soup, url)

            # Обработка PDF файлов
            files_content = []
            for pdf_url in list(links['files']['pdf'])[:3]:  # Ограничиваем количество
                result = self.extract_from_pdf(pdf_url)
                if result['text']:
                    files_content.append({
                        'type': 'PDF',
                        'url': pdf_url,
                        'content': result['text'][:10000] + "..." if len(result['text']) > 10000 else result['text'],
                        'local_path': result['local_path']
                    })

            # Сохранение данных страницы
            self.data.append({
                'url': url,
                'text': main_text,
                'images': img_texts,
                'metadata': metadata,
                'links': {
                    'internal': list(links['internal']),
                    'external': list(links['external']),
                    'files': {k: list(v) for k, v in links['files'].items()}
                },
                'files_content': files_content
            })

            # Рекурсивный обход внутренних ссылок
            for link in list(links['internal'])[:5]:  # Ограничиваем количество
                self.scrape_page(link)

        except Exception as e:
            print(f"Ошибка при обработке {url}: {str(e)}")

    def extract_from_pdf(self, pdf_url: str) -> Dict[str, Optional[str]]:
        """
        Извлекает текст из PDF файла

        Args:
            pdf_url: URL PDF файла

        Returns:
            Словарь с текстом и путем к локальному файлу
        """
        try:
            response = self.session.get(pdf_url, stream=True)
            if int(response.headers.get('content-length', 0)) > self.max_file_size:
                return {'text': None, 'local_path': None}

            local_path = self.download_file(pdf_url, 'pdf') if self.download_documents else None

            with BytesIO(response.content) as pdf_file:
                text = pdf_extract_text(pdf_file)
                return {
                    'text': self.clean_text(text),
                    'local_path': local_path
                }
        except Exception as e:
            print(f"Ошибка обработки PDF {pdf_url}: {str(e)}")
            return {'text': None, 'local_path': None}

    def run(self) -> List[Dict]:
        """Запускает парсинг сайта"""
        self.scrape_page(self.root_url)
        return self.data

    def save_results(self, output_dir: str = 'scrape_results') -> None:
        """Сохраняет результаты в JSON и текстовый файл"""
        os.makedirs(output_dir, exist_ok=True)

        # Сохранение в JSON
        with open(os.path.join(output_dir, 'full_data.json'), 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=4)

        # Сохранение в текстовый файл
        with open(os.path.join(output_dir, 'full_data.txt'), 'w', encoding='utf-8') as f:
            for page in self.data:
                f.write(f"\n{'=' * 80}\nURL: {page['url']}\n{'=' * 80}\n\n")

                if page['metadata']['title']:
                    f.write(f"Заголовок: {page['metadata']['title']}\n")

                f.write(f"\nОсновной текст:\n{page['text']}\n")

                if page['images']:
                    f.write("\nТекст с изображений:\n")
                    for img in page['images']:
                        f.write(f"\nИзображение: {img['url']}\n")
                        if img['alt_text']:
                            f.write(f"Описание: {img['alt_text']}\n")
                        f.write(f"Текст: {img['ocr_text']}\n")

                if page['files_content']:
                    f.write("\nСодержимое файлов:\n")
                    for file in page['files_content']:
                        f.write(f"\nФайл: {file['url']}\n{file['content']}\n")


def start(url: str) -> None:
    """
    Запускает процесс парсинга сайта

    Args:
        url: URL сайта для парсинга
    """
    scraper = CompleteWebsiteScraper(
        root_url=url,
        max_pages=20,
        ocr_enabled=True,
        download_documents=True
    )

    print("Начало сканирования сайта...")
    scraper.run()
    scraper.save_results()

    print("\nСканирование завершено!")
    print("Результаты сохранены в папке scrape_results:")
    print("- full_data.json (JSON формат)")
    print("- full_data.txt (текстовый формат)")