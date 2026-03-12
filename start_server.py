#!/usr/bin/env python3
"""
HTTP-сервер с Basic Auth для раздачи книг.
Запуск: python serve.py
Логин/пароль: books / 3011 (измените в коде при необходимости)
"""

import http.server
import socketserver
import os
import base64
from urllib.parse import unquote

# Настройки
PORT = 8080
HOST = "0.0.0.0"  # Слушать все интерфейсы
USERNAME = "books"
PASSWORD = "3011"  # Измените на свой пароль!

# Директория для раздачи (папка hfs)
BASE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "hfs")
BOOKS_DIR = os.path.join(BASE_DIR, "books")
IMAGES_DIR = os.path.join(BASE_DIR, "images")


class BasicAuthHandler(http.server.SimpleHTTPRequestHandler):
    """Обработчик с HTTP Basic Auth."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=BASE_DIR, **kwargs)

    def do_AUTHHEAD(self):
        self.send_response(401)
        self.send_header("WWW-Authenticate", 'Basic realm="MomBooks"')
        self.send_header("Content-Type", "text/html")
        self.end_headers()

    def check_auth(self):
        auth_header = self.headers.get("Authorization")
        if not auth_header:
            print(f"⚠️ Нет заголовка Authorization")
            return None

        try:
            auth_type, auth_data = auth_header.split()
            if auth_type.lower() != "basic":
                print(f"⚠️ Неверный тип auth: {auth_type}")
                return None

            decoded = base64.b64decode(auth_data).decode("utf-8")
            username, password = decoded.split(":", 1)
            print(f"🔐 Проверка: {username}:{password}")
            return (username, password)
        except Exception as e:
            print(f"⚠️ Ошибка парсинга auth: {e}")
            return None

    def do_GET(self):
        # Проверка авторизации
        auth = self.check_auth()
        if auth is None or auth[0] != USERNAME or auth[1] != PASSWORD:
            self.do_AUTHHEAD()
            self.wfile.write(b"<html><body><h1>401 Unauthorized</h1><p>Trebuetsya avtorizatsiya</p></body></html>")
            return

        # Декодируем URL (кириллица) - убираем ведущий /
        decoded_path = unquote(self.path).lstrip("/")

        # Если запрошен корень или папка — отдаём index.html
        if not decoded_path or decoded_path.endswith("/"):
            decoded_path += "index.html"
            full_path = os.path.normpath(os.path.join(BASE_DIR, decoded_path))
        # Обложки из папки images/
        elif decoded_path.startswith("images/"):
            full_path = os.path.normpath(os.path.join(IMAGES_DIR, decoded_path[7:]))
        # Книги из папки books/
        elif decoded_path.startswith("books/"):
            full_path = os.path.normpath(os.path.join(BOOKS_DIR, decoded_path[6:]))
        else:
            full_path = os.path.normpath(os.path.join(BASE_DIR, decoded_path))

        print(f"📁 Запрос пути: {decoded_path}")
        print(f"📁 Полный путь: {full_path}")
        print(f"📁 Файл существует: {os.path.isfile(full_path)}")

        # Проверяем существование файла
        if not os.path.isfile(full_path):
            print(f"❌ 404: {full_path}")
            self.send_error(404)
            return

        # Отдаём файл
        with open(full_path, "rb") as f:
            content = f.read()

        # Определяем MIME-тип
        mime = "application/epub+zip" if decoded_path.endswith(".epub") else "image/jpeg" if decoded_path.endswith(".jpg") else "text/html"

        self.send_response(200)
        self.send_header("Content-Type", mime)
        self.send_header("Content-Length", len(content))
        self.end_headers()
        self.wfile.write(content)

    def send_error(self, code, message=None, explain=None):
        """Переопределяем для избежания UnicodeEncodeError с кириллицей."""
        # Не передаём кириллический путь в message
        super().send_error(code, message, explain)

    def log_message(self, format, *args):
        """Логирование запросов."""
        print(f"[{self.log_date_time_string()}] {args[0]}")


class ReuseAddrServer(socketserver.TCPServer):
    allow_reuse_address = True


if __name__ == "__main__":
    with ReuseAddrServer((HOST, PORT), BasicAuthHandler) as httpd:
        print(f"📚 Сервер запущен: http://{HOST}:{PORT}")
        print(f"🔐 Логин: {USERNAME} / Пароль: {PASSWORD}")
        print(f"📁 Корневая папка: {BASE_DIR}")
        print("⚡ Нажмите Ctrl+C для остановки")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n⛔ Остановка сервера...")
