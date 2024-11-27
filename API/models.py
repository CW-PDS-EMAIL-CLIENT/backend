from pydantic import BaseModel
from typing import List, Optional
from fastapi import UploadFile

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
    attachments: Optional[List[UploadFile]] = None  # Используем UploadFile для загрузки файлов
    private_key_sign: Optional[str] = None
    public_key_encrypt: Optional[str] = None  # Ключи для шифрования

# API для авторизации под другим Email
class ChangeAccountRequest(BaseModel):
    email_user: str
    email_pass: str
    imap_server: Optional[str] = None
    smtp_server: Optional[str] = None
    port: Optional[int] = None

# Определение моделей данных для получения списка писем
class SummaryEmailResponse(BaseModel):
    id: int
    sender: str
    subject: str
    date: str

class FetchEmailsRequest(BaseModel):
    folder_name: Optional[str] = "Inbox"
    offset: Optional[int] = None
    limit: Optional[int] = None

class FetchEmailsResponse(BaseModel):
    emailsList: List[SummaryEmailResponse]

# Модели данных для авторизации
class AccountCredentials(BaseModel):
    email_user: str
    email_pass: str
    imap_server: Optional[str] = "imap.mail.ru"  # Значение по умолчанию
    smtp_server: Optional[str] = "smtp.mail.ru"  # Значение по умолчанию
    imap_port: Optional[int] = 993  # Значение по умолчанию
    smtp_port: Optional[int] = 587  # Значение по умолчанию

# API для получения информации о конкретном письме
class FetchEmailInfoRequest(BaseModel):
    email_id: int
    folder_name: Optional[str] = "Inbox"

class FetchEmailInfoResponse(BaseModel):
    sender: str
    to: str
    subject: str
    date: str
    body: str
    attachments: Optional[List[str]] = None

    class Config:
        arbitrary_types_allowed = True

# API для генерации ключей и отправки по почте
class KeyGenerationResponse(BaseModel):
    private_key_sign: str
    public_key_sign: str
    private_key_encrypt: str
    public_key_encrypt: str

# API для отправки письма на указанную почту
class SendEmailResponse(BaseModel):
    message: str

    class EmailData(BaseModel):
        sender_email: str
        recipient_email: str
        public_key_sign: str
        public_key_encrypt: str
        create_date: str
