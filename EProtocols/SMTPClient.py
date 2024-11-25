import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from email.header import Header
from email.utils import formataddr, formatdate


class SMTPClient:
    def __init__(self, smtp_server, email_user, email_pass, port=587, timeout=5):
        self.smtp_server = smtp_server
        self.email_user = email_user
        self.email_pass = email_pass
        self.port = port
        self.timeout = timeout
        self.server = None

    def open_connect(self):
        """Открывает соединение с SMTP-сервером."""
        if not self.server:
            self.server = smtplib.SMTP(self.smtp_server, self.port, timeout=self.timeout)
            self.server.starttls()  # Обеспечивает безопасное соединение
            self.server.login(self.email_user, self.email_pass)

    def close_connect(self):
        """Закрывает соединение с SMTP-сервером."""
        if self.server:
            self.server.quit()
            self.server = None

    def change_account(self, new_email_user, new_email_pass, new_smtp_server=None, new_port=None):
        """
        Меняет учетные данные и параметры подключения для SMTP.
        """
        # Закрываем текущее соединение
        self.close_connect()

        # Обновляем учетные данные и параметры подключения
        self.email_user = new_email_user
        self.email_pass = new_email_pass
        if new_smtp_server:
            self.smtp_server = new_smtp_server
        if new_port:
            self.port = new_port

        # Открываем новое соединение с новыми учетными данными
        self.open_connect()
        print(f"Авторизация выполнена с новым аккаунтом: {self.email_user} на сервере {self.smtp_server}:{self.port}")

    def send_email(self, to_email, subject, body, from_name=None, to_name=None, attachments=None):
        """
        Отправляет письмо через SMTP-сервер.

        :param to_email: Email-адрес получателя.
        :param subject: Тема письма.
        :param body: Содержимое письма.
        :param from_name: Имя отправителя (опционально).
        :param to_name: Имя получателя (опционально).
        :param attachments: Список вложений в виде [{"filename": имя, "content": байты}, ...].
        """
        if not self.server:
            raise Exception("Соединение с SMTP-сервером не установлено.")

        # Создаем сообщение
        msg = MIMEMultipart()
        msg['From'] = formataddr((str(Header(from_name, 'utf-8')), self.email_user) if from_name else self.email_user)
        msg['To'] = formataddr((str(Header(to_name, 'utf-8')), to_email) if to_name else to_email)
        msg['Subject'] = Header(subject, 'utf-8')
        msg['Date'] = formatdate(localtime=True)  # Генерация текущей даты и времени

        # Добавляем тело письма
        msg.attach(MIMEText(body, 'plain', 'utf-8'))

        # Обработка вложений
        if attachments:
            for attachment in attachments:
                part = MIMEBase('application', 'octet-stream')
                part.set_payload(attachment["content"])
                encoders.encode_base64(part)
                part.add_header(
                    'Content-Disposition',
                    f'attachment; filename="{attachment["filename"]}"'
                )
                msg.attach(part)

        # Отправляем письмо
        self.server.sendmail(self.email_user, to_email, msg.as_string())

        return msg

if __name__ == '__main__':
    smtp_server = "smtp.mail.ru"
    email_user = "donntu_test@mail.ru"
    email_pass = "wrixCgaMYsqXWmVbBPS7"

    # Создаем экземпляр SMTPClient
    client = SMTPClient(smtp_server, email_user, email_pass)

    # Открываем соединение
    client.open_connect()

    # Указываем путь к файлу
    file_path = "C:\\Users\\User\\Downloads\\example.txt"

    # Отправляем письмо
    try:
        # Открываем файл в бинарном режиме
        with open(file_path, "rb") as file:
            attachment_content = file.read()

        client.send_email(
            to_email="20egorka03@gmail.com",
            subject="Тестовое письмо",
            body="Это тестовое письмо, отправленное через SMTP.",
            from_name="Тест Отправитель",
            to_name="Тест Получатель",
            attachments=[
                {"filename": file.name, "content": attachment_content},
                {"filename": file.name, "content": attachment_content},
                {"filename": file.name, "content": attachment_content},
                {"filename": file.name, "content": attachment_content}
            ]
        )
        print("Письмо успешно отправлено!")
    except Exception as e:
        print(f"Ошибка при отправке письма: {e}")

    # Закрываем соединение
    client.close_connect()
