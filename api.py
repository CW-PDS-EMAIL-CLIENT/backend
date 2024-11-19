from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional
from IMAPClient import IMAPClient  # Используем существующий IMAPClient
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

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

# Остановка IMAP-клиента при завершении работы сервера
@app.on_event("shutdown")
def shutdown_event():
    imapClient.close_connect()
