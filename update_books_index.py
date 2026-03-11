#!/usr/bin/env python3
"""
update_books_index.py - Скрипт для сканирования книг и генерации index.html

Сканирует папку hfs/books, извлекает метаданные из epub файлов,
генерирует обложки для книг без обложек и создаёт index.html
в виде книжной полки для HFS (Http File Server).
"""

import os
import sys
import urllib.parse
from datetime import datetime, timedelta
from pathlib import Path
from ebooklib import epub
from PIL import Image, ImageDraw, ImageFont


# Константы
BOOKS_DIR = Path(__file__).parent / "hfs" / "books"
IMAGES_DIR = Path(__file__).parent / "hfs" / "images"
INDEX_FILE = Path(__file__).parent / "hfs" / "index.html"
NEW_BOOKS_DAYS = 14  # Период для "новых" книг (2 недели)


def ensure_dirs():
    """Убедиться, что необходимые папки существуют."""
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)


def get_epub_metadata(epub_path: Path) -> dict:
    """
    Извлечь метаданные из epub файла.
    
    Возвращает dict с полями:
    - title: название
    - author: автор
    - year: год издания
    - has_cover: есть ли встроенная обложка
    - cover_data: данные обложки (bytes) или None
    """
    try:
        book = epub.read_epub(str(epub_path))
    except Exception as e:
        print(f"  Ошибка чтения {epub_path.name}: {e}")
        return None
    
    # Извлечение названия
    title = book.title or epub_path.stem
    
    # Извлечение автора
    creators = book.get_metadata("http://purl.org/dc/elements/1.1/", "creator")
    author = creators[0][0] if creators else "Неизвестный автор"
    
    # Извлечение года
    dates = book.get_metadata("http://purl.org/dc/elements/1.1/", "date")
    year = dates[0][0][:4] if dates else None
    
    # Поиск обложки
    cover_data = None
    has_cover = False
    
    from ebooklib import ITEM_IMAGE, ITEM_COVER
    for item in book.get_items():
        if item.get_type() in (ITEM_IMAGE, ITEM_COVER):
            if "cover" in item.get_name().lower() or item.id == "id1":
                cover_data = item.get_content()
                has_cover = True
                break
    
    return {
        "title": title,
        "author": author,
        "year": year,
        "has_cover": has_cover,
        "cover_data": cover_data,
    }


def generate_cover_image(title: str, author: str, year: str, output_path: Path):
    """
    Сгенерировать обложку книги с текстом.
    
    Верх: автор
    Центр: название (крупно)
    Низ: год
    """
    # Размеры обложки
    width, height = 400, 600
    background_color = (45, 55, 70)  # Тёмно-синий фон
    text_color = (255, 255, 255)
    accent_color = (255, 215, 0)  # Золотой для названия
    
    img = Image.new("RGB", (width, height), background_color)
    draw = ImageDraw.Draw(img)
    
    # Попытка загрузить шрифты
    try:
        # Пробуем разные шрифты для кириллицы
        font_paths = [
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/times.ttf",
            "C:/Windows/Fonts/georgia.ttf",
        ]
        font_title = ImageFont.truetype(font_paths[0], 32)
        font_author = ImageFont.truetype(font_paths[0], 24)
        font_year = ImageFont.truetype(font_paths[0], 28)
    except Exception:
        font_title = ImageFont.load_default()
        font_author = font_title
        font_year = font_title
    
    # Текст автора (сверху)
    author_text = author[:50] + "..." if len(author) > 50 else author
    bbox = draw.textbbox((0, 0), author_text, font=font_author)
    author_width = bbox[2] - bbox[0]
    author_x = (width - author_width) // 2
    draw.text((author_x, 40), author_text, fill=text_color, font=font_author)
    
    # Название (по центру, крупно)
    # Разбиваем на строки если длинное
    title_lines = []
    words = title.split()
    current_line = ""
    for word in words:
        if len(current_line) + len(word) < 35:
            current_line += " " + word if current_line else word
        else:
            title_lines.append(current_line)
            current_line = word
    if current_line:
        title_lines.append(current_line)
    
    # Рассчитываем позицию для центрирования блока заголовка
    line_height = 50
    total_height = len(title_lines) * line_height
    start_y = (height - total_height) // 2 - 30
    
    for i, line in enumerate(title_lines):
        bbox = draw.textbbox((0, 0), line, font=font_title)
        line_width = bbox[2] - bbox[0]
        line_x = (width - line_width) // 2
        line_y = start_y + i * line_height
        draw.text((line_x, line_y), line, fill=accent_color, font=font_title)
    
    # Год (снизу)
    if year:
        year_text = str(year)
        bbox = draw.textbbox((0, 0), year_text, font=font_year)
        year_width = bbox[2] - bbox[0]
        year_x = (width - year_width) // 2
        draw.text((year_x, height - 80), year_text, fill=text_color, font=font_year)
    
    # Сохраняем
    img.save(output_path, "JPEG", quality=90)
    print(f"  Сгенерирована обложка: {output_path.name}")


def scan_books() -> dict:
    """
    Отсканировать все epub файлы в папке books.
    
    Возвращает dict:
    - folders: {folder_name: [book_info, ...]}
    - root: [book_info, ...]  # книги в корневой папке
    - new: [book_info, ...]  # новые книги за 2 недели
    """
    folders = {}
    root = []
    new_books = []
    
    cutoff_date = datetime.now() - timedelta(days=NEW_BOOKS_DAYS)
    
    # Рекурсивный обход папки books
    for epub_path in BOOKS_DIR.rglob("*.epub"):
        # Пропускаем не-epub файлы (на случай .zip и др.)
        if not epub_path.is_file():
            continue
        
        print(f"Обработка: {epub_path.relative_to(BOOKS_DIR)}")
        
        # Получаем метаданные
        metadata = get_epub_metadata(epub_path)
        if metadata is None:
            continue
        
        # Определяем относительный путь
        try:
            rel_path = epub_path.relative_to(BOOKS_DIR)
        except ValueError:
            continue
        
        # Путь для URL (forward slashes + URL encoding для кириллицы и пробелов)
        url_path = "/".join(urllib.parse.quote(part) for part in rel_path.parts)
        
        # Имя обложки (совпадает с именем epub, но .jpg)
        cover_filename = epub_path.stem + ".jpg"
        cover_path = IMAGES_DIR / cover_filename
        
        # Если есть встроенная обложка - сохраняем
        if metadata["has_cover"] and metadata["cover_data"]:
            with open(cover_path, "wb") as f:
                f.write(metadata["cover_data"])
            print(f"  Сохранена обложка из epub")
        else:
            # Генерируем обложку
            print(f"  Генерация обложки...")
            generate_cover_image(
                metadata["title"],
                metadata["author"],
                metadata["year"] or "",
                cover_path,
            )
        
        # Информация о книге
        book_info = {
            "title": metadata["title"],
            "author": metadata["author"],
            "year": metadata["year"],
            "url_path": url_path,
            "cover_url": f"images/{urllib.parse.quote(cover_filename)}",
            "file_modified": datetime.fromtimestamp(epub_path.stat().st_mtime),
        }
        
        # Определяем папку
        if rel_path.parent == Path("."):
            # Корневая папка
            root.append(book_info)
        else:
            # Подпапка (первый уровень)
            folder_name = rel_path.parts[0]
            if folder_name not in folders:
                folders[folder_name] = []
            folders[folder_name].append(book_info)
        
        # Проверяем на "новизну"
        if book_info["file_modified"] > cutoff_date:
            new_books.append(book_info)
    
    return {
        "folders": folders,
        "root": root,
        "new": new_books,
    }


def generate_html(data: dict) -> str:
    """Сгенерировать HTML страницу книжной полки."""
    
    def book_card(book: dict) -> str:
        """HTML карточки книги."""
        title_escaped = book["title"].replace('"', "&quot;")
        return f'''
        <div class="book-card">
            <a href="{book["url_path"]}">
                <img src="{book["cover_url"]}" alt="{title_escaped}" loading="lazy">
            </a>
            <div class="book-info">
                <div class="book-author">{book["author"]}</div>
                <div class="book-title" title="{title_escaped}">{book["title"]}</div>
                {f'<div class="book-year">{book["year"]}</div>' if book["year"] else ""}
            </div>
        </div>
        '''
    
    def books_row(books: list) -> str:
        """HTML ряд книг."""
        if not books:
            return ""
        cards = "\n".join(book_card(b) for b in sorted(books, key=lambda x: x["title"]))
        return f'<div class="books-row">\n{cards}\n</div>'
    
    # Сортируем папки по алфавиту
    sorted_folders = sorted(data["folders"].keys())
    
    # Генерируем секцию "Новое"
    new_section = ""
    if data["new"]:
        new_books_html = books_row(data["new"])
        new_section = f'''
        <section class="section new-books">
            <h2>🆕 Новое</h2>
            {new_books_html}
        </section>
        '''
    
    # Генерируем секции папок
    folders_sections = ""
    for folder_name in sorted_folders:
        books = data["folders"][folder_name]
        books_html = books_row(books)
        folders_sections += f'''
        <section class="section folder">
            <h2>📁 {folder_name}</h2>
            {books_html}
        </section>
        '''
    
    # Генерируем секцию корневых книг
    root_section = ""
    if data["root"]:
        root_books_html = books_row(data["root"])
        root_section = f'''
        <section class="section root-books">
            <h2>📚 Книги в корневой папке</h2>
            {root_books_html}
        </section>
        '''
    
    # Полный HTML
    html = f'''<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Домашняя библиотека</title>
    <style>
        * {{
            box-sizing: border-box;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: #eee;
            margin: 0;
            padding: 20px;
            min-height: 100vh;
        }}
        h1 {{
            text-align: center;
            color: #ffd700;
            margin-bottom: 10px;
        }}
        .subtitle {{
            text-align: center;
            color: #888;
            margin-bottom: 30px;
        }}
        .section {{
            margin-bottom: 40px;
        }}
        .section h2 {{
            border-bottom: 2px solid #ffd700;
            padding-bottom: 10px;
            margin-bottom: 20px;
            color: #ffd700;
        }}
        .books-row {{
            display: flex;
            flex-wrap: wrap;
            gap: 20px;
            justify-content: flex-start;
        }}
        .book-card {{
            background: rgba(255, 255, 255, 0.05);
            border-radius: 10px;
            overflow: hidden;
            width: 160px;
            transition: transform 0.2s, box-shadow 0.2s;
        }}
        .book-card:hover {{
            transform: translateY(-5px);
            box-shadow: 0 10px 30px rgba(255, 215, 0, 0.2);
        }}
        .book-card img {{
            width: 100%;
            height: 240px;
            object-fit: cover;
            display: block;
        }}
        .book-info {{
            padding: 12px;
        }}
        .book-author {{
            font-size: 12px;
            color: #aaa;
            margin-bottom: 4px;
        }}
        .book-title {{
            font-size: 14px;
            font-weight: 600;
            color: #fff;
            overflow: hidden;
            text-overflow: ellipsis;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            min-height: 40px;
        }}
        .book-year {{
            font-size: 12px;
            color: #888;
            margin-top: 6px;
        }}
        .book-card a {{
            text-decoration: none;
            color: inherit;
        }}
        /* Адаптивность для iPad */
        @media (max-width: 768px) {{
            .book-card {{
                width: 120px;
            }}
            .book-card img {{
                height: 180px;
            }}
        }}
    </style>
</head>
<body>
    <h1>📚 Домашняя библиотека</h1>
    <p class="subtitle">Нажмите на книгу для загрузки</p>
    
    {new_section}
    {folders_sections}
    {root_section}
</body>
</html>
'''
    return html


def main():
    """Основная функция."""
    print("=" * 50)
    print("Сканирование книг и генерация index.html")
    print("=" * 50)
    
    # Убедиться, что папки существуют
    ensure_dirs()
    
    # Сканирование книг
    print("\n📖 Сканирование книг...")
    data = scan_books()
    
    total_books = (
        sum(len(books) for books in data["folders"].values()) +
        len(data["root"])
    )
    print(f"\nНайдено книг: {total_books}")
    print(f"Папок: {len(data['folders'])}")
    print(f"Новых книг (за 2 недели): {len(data['new'])}")
    
    # Генерация HTML
    print("\n📄 Генерация index.html...")
    html = generate_html(data)
    
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    
    print(f"\n✅ Готово! Файл сохранён: {INDEX_FILE}")
    print("\nОткройте http://<ваш-ip>/index.html в браузере iPad")


if __name__ == "__main__":
    main()
