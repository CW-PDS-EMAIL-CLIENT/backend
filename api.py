import os.path
import json
import re
from contextlib import asynccontextmanager

import base64

import uvicorn
from fastapi import FastAPI, HTTPException, Form, UploadFile, File
from pydantic import BaseModel
from typing import List, Optional

from DB.RSAKeyDatabase import RSAKeyDatabase
from EProtocols.IMAPClient import IMAPClient  # Используем существующий IMAPClient
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from EProtocols.SMTPClient import SMTPClient
from SecureEmailClient import SecureEmailClient

# Использование lifespan для событий старта и остановки
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Инициализация при старте
    await db.connect()
    await db.create_tables()
    print("Приложение запущено!")
    yield
    # Очистка при завершении
    # Остановка IMAP-клиента при завершении работы сервера
    imapClient.close_connect()
    await db.disconnect()
    print("Приложение завершено!")


app = FastAPI(lifespan=lifespan)

# Инициализация gRPC клиента
secure_email_client = SecureEmailClient()

# Настройка CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8080"],  # URL фронтенда, которому разрешён доступ
    allow_credentials=True,
    allow_methods=["*"],  # Разрешённые HTTP-методы
    allow_headers=["*"],  # Разрешённые заголовки
)

# Инициализация IMAP-клиента
imap_server = "imap.mail.ru"
email_user = "donntu_test@mail.ru"  # modex.modex@mail.ru   #   donntu_test@mail.ru
email_pass = "wrixCgaMYsqXWmVbBPS7" # MsJE9vLGRFkDV6ECMLdF  #   wrixCgaMYsqXWmVbBPS7

imapClient = IMAPClient(imap_server, email_user, email_pass)
imapClient.open_connect()

# Инициализация SMTP-клиента
smtp_server = "smtp.mail.ru"
smtp_email_user = "modex.modex@mail.ru"
smtp_email_pass = "wqCgQPseQDsBZCk9Zd03"

smtpClient = SMTPClient(smtp_server, smtp_email_user, smtp_email_pass)

db = RSAKeyDatabase()

user_encrypt = True

# Определение моделей данных
class SummaryEmailResponse(BaseModel):
    id: int
    sender: str
    subject: str
    date: str


class FetchEmailsResponse(BaseModel):
    emailsList: List[SummaryEmailResponse]


class FetchEmailInfoResponse(BaseModel):
    sender: str
    to: str
    subject: str
    date: str
    body: str
    attachments: Optional[List[str]] = None

    class Config:
        arbitrary_types_allowed = True

class SaveAttachmentsRequest(BaseModel):
    save_path: str

class SaveAttachmentsResponse(BaseModel):
    message: str

# API для отправки писем
# Модели данных
class SendEmailRequest(BaseModel):
    to_email: str
    subject: str
    body: str
    from_name: Optional[str] = None
    to_name: Optional[str] = None
    attachments: Optional[List[UploadFile]] = File(None)  # Используем UploadFile для загрузки файлов
    private_key_sign: Optional[str] = None
    public_key_encrypt: Optional[str] = None  # Ключи для шифрования


class SendEmailResponse(BaseModel):
    message: str

# API для получения списка писем
@app.get("/emails/", response_model=FetchEmailsResponse)
async def fetch_emails(offset: Optional[int] = 0, limit: Optional[int] = None):
    emails = imapClient.fetch_emails(offset, limit)
    emails_list = [
        SummaryEmailResponse(
            id=email["id"],
            sender=email["sender"],
            subject=email["subject"],
            date=email["date"]
        ) for email in emails
    ]
    return FetchEmailsResponse(emailsList=emails_list)

# Глобальный массив для хранения вложений
global_attachments = []

# Если почта может быть без угловых скобок, оставляем только email
def extract_email(sender):
    email_pattern = r'<(.+?)>'
    match = re.search(email_pattern, sender)
    if match:
        return match.group(1)
    elif '@' in sender:  # Если строка уже является email
        return sender
    else:
        return None

# API для получения информации о конкретном письме
@app.get("/emails/{email_id}", response_model=FetchEmailInfoResponse)
async def fetch_email_info(email_id: int):
    """
    API для получения информации о письме с декодированием Base64 и автоматическим дешифрованием.

    Args:
        email_id (int): ID письма.

    Returns:
        FetchEmailInfoResponse: Информация о письме.

    Raises:
        HTTPException: Ошибка, если письмо не найдено или ключи не подошли.
    """
    global global_attachments
    global_attachments.clear()  # Очищаем предыдущие вложения

    try:
        # Получаем информацию о письме
        email_info = imapClient.fetch_email_info(str(email_id).encode())
        if not email_info:
            raise HTTPException(status_code=404, detail="Email not found")

        encrypted_body = email_info.get("body")
        encrypted_attachments = email_info.get("attachments", [])
        decrypted_body = None
        decrypted_attachments = []

        # Проверяем, является ли тело письма зашифрованным
        try:
            json_body = json.loads(encrypted_body)
            if all(key in json_body for key in ("iv", "encrypted_des_key", "signature", "encrypted_content")):

                sender_email = extract_email(email_info["sender"])

                # Работа с базой данных через менеджер контекста

                decryption_keys = await db.get_decrypt_keys(current_recipient_email=email_user, sender_email=sender_email)

                if not decryption_keys:
                    raise HTTPException(status_code=400, detail="No decryption or signing keys found.")

                # Попытка расшифровать с каждым набором ключей
                for key_pair in decryption_keys:
                    try:
                        private_key_encrypt = key_pair["private_key_encrypt"]
                        public_key_sign = key_pair["public_key_sign"]

                        # Декодируем данные из Base64
                        encrypted_email = {
                            "iv": base64.b64decode(json_body["iv"]),
                            "encrypted_des_key": base64.b64decode(json_body["encrypted_des_key"]),
                            "signature": base64.b64decode(json_body["signature"]),
                            "encrypted_content": base64.b64decode(json_body["encrypted_content"]),
                            "encrypted_attachments": [
                                {
                                    "filename": att["filename"],
                                    "content": base64.b64decode(att["content"])
                                }
                                for att in encrypted_attachments
                            ]
                        }

                        # Производим дешифрование
                        decrypted_email = secure_email_client.verify_email(
                            encrypted_email=encrypted_email,
                            private_key_encrypt=private_key_encrypt,
                            public_key_sign=public_key_sign
                        )
                        decrypted_body = decrypted_email.email_body  # Тело письма
                        decrypted_attachments = [
                            {"filename": att.filename, "content": att.content} for att in decrypted_email.attachments
                        ]  # Вложения
                    except Exception as e:
                        raise HTTPException(status_code=400, detail=f"Failed to decrypt email: {e}")

            else:
                # Если JSON-структура не содержит нужных ключей, возвращаем тело как есть
                decrypted_body = base64.b64decode(encrypted_body).decode("utf-8")  # Декодируем тело из Base64
                decrypted_attachments = [
                    {"filename": att["filename"], "content": base64.b64decode(att["content"])}
                    for att in encrypted_attachments
                ]
        except json.JSONDecodeError:
            # Если тело не является JSON, возвращаем как есть
            decrypted_body = encrypted_body
            decrypted_attachments = [{"filename": att["filename"], "content": att["content"]} for att in encrypted_attachments]

        # Сохраняем вложения во временные файлы и обновляем global_attachments
        attachments_dir = "attachments"
        os.makedirs(attachments_dir, exist_ok=True)
        for attachment in decrypted_attachments:
            file_path = os.path.join(attachments_dir, attachment["filename"])
            with open(file_path, "wb") as f:
                f.write(attachment["content"])
            global_attachments.append(file_path)

        # Возвращаем информацию о письме
        return FetchEmailInfoResponse(
            sender=email_info["sender"],
            to=email_info["to"],
            subject=email_info["subject"],
            date=email_info["date"],
            body=decrypted_body,
            attachments=[os.path.basename(f) for f in global_attachments],
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    except Exception as e:
        print(f"Ошибка при получении информации о письме: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to fetch email info: {e}")

@app.get("/attachments/{filename}")
async def get_attachment(filename: str):
    """
    API для загрузки вложения.

    Args:
        filename (str): Имя файла вложения.

    Returns:
        FileResponse: Файл вложения.
    """
    file_path = os.path.join("attachments", filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path, filename=filename)

# API для отправки письма на указанную почту
@app.post("/emails/send/", response_model=SendEmailResponse)
async def send_email(
    to_email: str = Form(...),
    subject: str = Form(...),
    body: str = Form(...),
    from_name: Optional[str] = Form(None),
    to_name: Optional[str] = Form(None),
    attachments: Optional[List[UploadFile]] = File(None)
):
    try:
        smtpClient.open_connect()

        # Преобразуем вложения в байтовый формат
        file_attachments = []
        if attachments:
            for file in attachments:
                content = await file.read()
                file_attachments.append({
                    "filename": file.filename,
                    "content": content,  # Оставляем в байтовом формате
                })

        # Проверяем, нужно ли шифрование
        if user_encrypt:
            encrypt_keys = await db.get_encrypt_sign_keys(
                current_sender_email=smtp_email_user,
                recipient_email=to_email
            )

            # Проверяем наличие ключей
            if not encrypt_keys:
                raise HTTPException(
                    status_code=400,
                    detail="There are no encryption keys available, generate new ones for this email address.",
                )

            # Получаем ключи
            private_key_sign = encrypt_keys["private_key_sign"]
            public_key_encrypt = encrypt_keys["public_key_encrypt"]

            # Преобразуем тело письма в байты
            body_bytes = body.encode("utf-8")

            encrypted_email = secure_email_client.process_email(
                email_body=body_bytes,
                attachments=file_attachments,
                private_key_sign=private_key_sign,
                public_key_encrypt=public_key_encrypt,
            )

            content_body = {
                "iv": base64.b64encode(encrypted_email.iv).decode("utf-8"),
                "encrypted_des_key": base64.b64encode(encrypted_email.encrypted_des_key).decode("utf-8"),
                "signature": base64.b64encode(encrypted_email.signature).decode("utf-8"),
                "encrypted_content": base64.b64encode(encrypted_email.encrypted_content).decode("utf-8")
            }

            body = json.dumps(content_body, ensure_ascii=False)

            # Корректное извлечение вложений
            file_attachments = []
            for attachment in encrypted_email.encrypted_attachments:
                # Предполагаем, что каждый элемент является объектом EncryptedAttachment
                file_attachments.append({
                    "filename": attachment.filename,  # Имена вложений
                    "content": base64.b64encode(attachment.content).decode("utf-8"),  # Контент зашифрованных вложений
                })

        # Отправка письма
        smtpClient.send_email(
            to_email=to_email,
            subject=subject,
            body=body,
            from_name=from_name,
            to_name=to_name,
            attachments=file_attachments,
        )
        smtpClient.close_connect()
        return SendEmailResponse(message="Email successfully sent.")
    except Exception as e:
        print(f"Error during email sending: {e}")
        smtpClient.close_connect()
        raise HTTPException(status_code=500, detail=f"Failed to send email: {e}")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)