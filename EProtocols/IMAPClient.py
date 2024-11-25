import imaplib
import email as em
from email.header import decode_header
import os

class IMAPClient:
    def __init__(self, imap_server, email_user, email_pass, port=993, timeout=5):
        self.imap_server = imap_server
        self.email_user = email_user
        self.email_pass = email_pass
        self.port = port
        self.timeout = timeout
        self.mail = None
        self.selected_email = None  # Переменная для хранения выбранного письма

    def open_connect(self):
        """Открывает соединение с почтовым сервером."""
        if not self.mail:
            self.mail = imaplib.IMAP4_SSL(self.imap_server, self.port)
            self.mail.sock.settimeout(self.timeout)  # Устанавливаем таймаут для текущего соединения
            self.mail.login(self.email_user, self.email_pass)
            self.mail.select("inbox")

    def close_connect(self):
        """Закрывает соединение с почтовым сервером."""
        if self.mail:
            self.mail.close()
            self.mail.logout()
            self.mail = None

    def change_account(self, new_email_user, new_email_pass, new_imap_server=None, new_port=None):
        """
        Меняет учетные данные и параметры подключения для IMAP.
        """
        # Закрываем текущее соединение
        self.close_connect()

        # Обновляем учетные данные и параметры подключения
        self.email_user = new_email_user
        self.email_pass = new_email_pass
        if new_imap_server:
            self.imap_server = new_imap_server
        if new_port:
            self.port = new_port

        # Открываем новое соединение с новыми учетными данными
        self.open_connect()
        print(f"Авторизация выполнена с новым аккаунтом: {self.email_user} на сервере {self.imap_server}:{self.port}")

    def decode_mime_words(self, s):
        """Декодирует закодированные слова в MIME-заголовке."""
        decoded_parts = []
        for part, encoding in decode_header(s):
            if isinstance(part, bytes):
                decoded_parts.append(part.decode(encoding or 'utf-8'))
            else:
                decoded_parts.append(part)
        return ''.join(decoded_parts)

    def is_connection_active(self):
        """Проверяет активность соединения с почтовым сервером."""
        try:
            status, _ = self.mail.noop()
            return status == "OK"
        except imaplib.IMAP4.abort:  # Соединение разорвано сервером
            return False
        except imaplib.IMAP4.error:  # Общая ошибка IMAP-соединения
            return False

    def fetch_emails(self, start=None, limit=None):
        """Получает список писем."""
        # Проверка на активность соединения перед запросом
        if not self.is_connection_active():
            print("Соединение потеряно. Переподключение...")
            self.close_connect()
            self.open_connect()

        # Ищем все письма
        status, messages = self.mail.search(None, "ALL")
        if status != "OK":
            print("Ошибка при поиске писем.")
            return []

        # Получаем список ID писем
        email_ids = messages[0].split()

        # Если указано ограничение, обрезаем список
        if start:
            email_ids = email_ids[start:]

        if limit:
            email_ids = email_ids[:limit]

        emails = []
        for email_id in reversed(email_ids):
            # Получаем содержимое письма
            status, msg_data = self.mail.fetch(email_id, "(RFC822)")
            if status != "OK":
                print(f"Ошибка при получении письма с ID {email_id}")
                continue

            # Парсим письмо
            msg = em.message_from_bytes(msg_data[0][1])

            # Декодируем заголовок
            subject = self.decode_mime_words(msg["Subject"])

            # Декодируем отправителя
            from_ = self.decode_mime_words(msg["From"])
            date = msg.get("Date")

            emails.append({"id": email_id, "sender": from_, "subject": subject, "date": date})

        return reversed(emails)

    def get_attachments(self, msg):
        """Извлекает все вложения из письма."""
        attachments = []
        for part in msg.walk():
            # Проверяем, есть ли вложение
            if part.get_content_disposition() == "attachment":
                filename = part.get_filename()
                if filename:
                    file_data = part.get_payload(decode=True)
                    attachments.append({
                        "filename": self.decode_mime_words(filename),
                        "content": file_data
                    })
        return attachments

    def fetch_email_info(self, email_id):
        """Получает полную информацию о письме по его ID, включая вложения."""
        try:
            # Проверяем состояние соединения
            if not self.mail.state == 'SELECTED':
                print("Reconnecting to IMAP server...")
                self.open_connect()

            status, msg_data = self.mail.fetch(email_id, "(RFC822)")

            # Проверка статуса и содержимого ответа
            if status != "OK" or not msg_data or not isinstance(msg_data[0], tuple):
                print(f"Письмо с ID {email_id} не найдено или недоступно.")
                return None

            # Если данные валидны, разбираем письмо
            msg = em.message_from_bytes(msg_data[0][1])
            self.selected_email = msg

            subject = self.decode_mime_words(msg["Subject"])
            from_ = self.decode_mime_words(msg["From"])
            to_ = self.decode_mime_words(msg["To"])
            date = msg.get("Date")
            body = self.get_body(msg)
            attachments = self.get_attachments(msg)

            return {
                "subject": subject,
                "sender": from_,
                "to": to_,
                "date": date,
                "body": body,
                "attachments": attachments
            }
        except Exception as e:
            print(f"Ошибка при обработке письма с ID {email_id}: {e}")
            return None

    def get_body(self, msg):
        """Извлекает тело письма."""
        if msg.is_multipart():
            for part in msg.walk():
                # Проверяем на текстовые части
                if part.get_content_type() == "text/plain":
                    return part.get_payload(decode=True).decode(part.get_content_charset() or 'utf-8')
        else:
            return msg.get_payload(decode=True).decode(msg.get_content_charset() or 'utf-8')

    def save_attachment(self, save_path):
        """Сохраняет вложения выбранного письма по указанному пути."""
        if not self.selected_email:
            raise ValueError("Письмо не выбрано. Сначала выберите письмо с помощью fetch_email_info().")

        # Извлекаем вложения из выбранного письма
        attachments = self.get_attachments(self.selected_email)
        if not attachments:
            print("У выбранного письма нет вложений.")
            return

        # Создаем папку, если она не существует
        if not os.path.exists(save_path):
            os.makedirs(save_path)

        for attachment in attachments:
            filename = attachment["filename"]
            content = attachment["content"]  # Байты данных вложения
            file_path = os.path.join(save_path, filename)

            with open(file_path, "wb") as file:
                file.write(content)  # Сохраняем байты данных в файл
            print(f"Вложение сохранено: {file_path}")

if __name__ == '__main__':
    imap_server = "imap.mail.ru"
    email_user = "donntu_test@mail.ru"
    email_pass = "wrixCgaMYsqXWmVbBPS7"

    # Создаем экземпляр класса IMAPClient
    client = IMAPClient(imap_server, email_user, email_pass)

    # Открываем соединение
    client.open_connect()

    # # Получаем и выводим письма
    # emails = client.fetch_emails(start=2, limit=2)
    # for email in emails:
    #     print("ID: ", email["id"])
    #     print("Sender:", email["sender"])
    #     print("Subject:", email["subject"])
    #     print("Date:", email["date"])
    #     print("-" * 50)

    # Показываем информацию о конкретном письме (например, о письме с ID 3)
    email_id = b'11'  # Замените на нужный ID письма
    email_info = client.fetch_email_info(email_id)
    if email_info:
        print("Full information about the email:")
        for key, value in email_info.items():
            print(f"{key}: {value}")
        print("-" * 50)

        # Сохраняем вложения письма в указанную папку
        try:
            client.save_attachment(r"C:\Users\User\Pictures\Attachments")
        except ValueError as e:
            print(e)

    # Закрываем соединение
    client.close_connect()