from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional
from IMAPClient import IMAPClient  # Используем существующий IMAPClient
from fastapi.middleware.cors import CORSMiddleware

from SMTPClient import SMTPClient
from gRPC_client import SecureEmailClient

app = FastAPI()

# Инициализация gRPC клиента
grpc_client = SecureEmailClient()

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
email_user = "donntu_test@mail.ru"
email_pass = "wrixCgaMYsqXWmVbBPS7"

imapClient = IMAPClient(imap_server, email_user, email_pass)
imapClient.open_connect()

# Инициализация SMTP-клиента
smtp_server = "smtp.mail.ru"
smtp_email_user = "donntu_test@mail.ru"
smtp_email_pass = "wrixCgaMYsqXWmVbBPS7"

smtpClient = SMTPClient(smtp_server, smtp_email_user, smtp_email_pass)

use_encrypt = True

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
    attachments: List[str]

class SaveAttachmentsRequest(BaseModel):
    save_path: str

class SaveAttachmentsResponse(BaseModel):
    message: str

# API для отправки писем
class SendEmailRequest(BaseModel):
    to_email: str
    subject: str
    body: str
    from_name: Optional[str] = None
    to_name: Optional[str] = None
    attachments: Optional[List[dict]] = None  # [{"filename": str, "content": bytes}]

class SendEmailResponse(BaseModel):
    message: str

# Предварительная инициализация
@app.on_event("startup")
async def startup_event():
    print("Приложение запущено!")

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

# API для получения информации о конкретном письме
@app.get("/emails/{email_id}", response_model=FetchEmailInfoResponse)
async def fetch_email_info(email_id: int):
    email_info = imapClient.fetch_email_info(str(email_id).encode())
    if not email_info:
        raise HTTPException(status_code=404, detail="Email not found")

    return FetchEmailInfoResponse(
        sender=email_info["sender"],
        to=email_info["to"],
        subject=email_info["subject"],
        date=email_info["date"],
        body=email_info["body"],
        attachments=[att["filename"] for att in email_info["attachments"]]
    )

def is_valid_path(path: str) -> bool:
    try:
        import os

        os.makedirs(path, exist_ok=True)
        return os.access(path, os.W_OK)
    except Exception:
        return False

# API для сохранения файла выбранного письма
@app.post("/emails/save_attachments", response_model=SaveAttachmentsResponse)
async def save_email_attachments(request: SaveAttachmentsRequest):
    try:
        save_path = request.save_path
        if not is_valid_path(save_path):
            raise ValueError("Invalid or inaccessible save path.")

        # Сохраняем вложения
        imapClient.save_attachment(save_path)
        return SaveAttachmentsResponse(message=f"Attachments saved to {save_path}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

# API для отправки письма на указанную почту
@app.post("/emails/send", response_model=SendEmailResponse)
async def send_email(request: SendEmailRequest):
    try:
        smtpClient.open_connect()  # Открываем соединение
        smtpClient.send_email(
            to_email=request.to_email,
            subject=request.subject,
            body=request.body,
            from_name=request.from_name,
            to_name=request.to_name,
            attachments=request.attachments or []  # Если None, передаем пустой список
        )
        smtpClient.close_connect()  # Закрываем соединение
        return SendEmailResponse(message="Email successfully send.")
    except Exception as e:
        smtpClient.close_connect()  # Закрываем соединение в случае ошибки
        raise HTTPException(status_code=500, detail=f"Failed to send email: {e}")

# Остановка IMAP-клиента при завершении работы сервера
@app.on_event("shutdown")
def shutdown_event():
    imapClient.close_connect()
