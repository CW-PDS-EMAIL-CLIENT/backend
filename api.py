import mimetypes
import os.path
import json
from contextlib import asynccontextmanager

import base64

import uvicorn
from fastapi import FastAPI, HTTPException, Query, Form, UploadFile, File
from pydantic import BaseModel, Field
from typing import List, Optional
from IMAPClient import IMAPClient  # Используем существующий IMAPClient
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from SMTPClient import SMTPClient
from SecureEmailClient import SecureEmailClient

# Использование lifespan для событий старта и остановки
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Инициализация при старте
    print("Приложение запущено!")
    yield
    # Очистка при завершении
    # Остановка IMAP-клиента при завершении работы сервера
    imapClient.close_connect()
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
    # Локальный массив ключей
    decryption_keys = [
        {
            "private_key_encrypt": "LS0tLS1CRUdJTiBSU0EgUFJJVkFURSBLRVktLS0tLQpNSUlFb3dJQkFBS0NBUUVBbENaK3dJY3I1ZW44K2UxSU80NzhMQVVsVEc1VmdwNFIvQ2ltWUtCUkl6K1RsTXhOCjNPYU9xNFIxQUJRTWNwNEdEbUVLMXFzdGh4WllPVFIrdC9GU0s5VHYyQVVTSDliL1c5Ui95WmR0QTlrdisvVFMKM3hEd3daMDBMOXJzajQ0Sm52R1l6WlpVeDBod29WSXZXVVFwWU01ZTE5UFo3QnpsOTF3MC9RaGtHVkZaVVhXZApSUmFBQ3hjQTEwWG1uYTR0NHVuYzlvMzdFWE81OFBjb1h1M1pYSGZWRnRTRTZvQzFaNFlLZkxXYnBnRWYza0pBCjk2dVMxQk1OMkdrV1FWUytlR1ROdEl5aHdHei9KY0M4VndYcURLUjRMSDRDY28vSk93WlVFV1d1bDhhSGJZdm0Kb0ZIb0ZMM0JtcUNEZzYxa0JQOTBLcFpNdjRxanBVdFRoSjhWZHdJREFRQUJBb0lCQUR6SXdvNnBweGd3OWN0eApVSWFuTnMyMDJzWE9LeVZwUjRYSEErUjNRbk1NM2JkYVQ4UUhrSmZNdzloaFlXNFJhZml5VmlrWG1KbHBVSTgvCis1SHE0RVQ5bTk1c3ppL2tIV2VHKzFzeDF0ZVNYNzZuaDNGZ1dQZUhVV2NsRXBRZnVkRE4zVnpVaGpveGZZeWkKMUt4eWErdTlJR3E3RUJseERlVjhubjBHMlZNTlRxS0NlSk84Y0JyNm9VZmxMYzB0K2Jnamhad2JGVE54NVlGSApMc1hhR1lVNFBWTlhKNFp2cFdOZ3oxdGV3K3BZdUhEWVFMQW5hUTRPUWhmdmFWMVN0bkxaK0dOWTdna2Z6NzZqCkJPZmV1azBMd2UrRndHeFZ4bUlUSjdLaC9lZUYydThYNFh2TVVqOEFSYXV5SmhHbVZ5T0t2N1lBTW9EamhQSkcKalloR2VPa0NnWUVBd2toZUd3aS8vUEpwaVoxcXhKYzVYY2pnamlwYzBidUxjQ2cvNkM2MmxJWWFzUGpMT05CZQpDUHFYWUNoS0RhSVU3b3ZwdFEwRHBrYXA2UXB0VU5jY2pSQXFGV2d1QWxZRHg3SDdTWHJqRVE4dVh4LzFHNDdxCis0Tk1mRXRQR2htSnpPMStuNTFLWlNKNlZkbUZZTmM1Y3kyT2t3c1gxeERSdTA4dnlFVG1oUXNDZ1lFQXd6YUQKZ29Uem1wYmR6eGlwcURsNFRHUndEb2NIRTlCZXhkaDV0WDNaSjJ6VWZJVXlmQmwxTmFDQTdIVlNmbWFER3liNwpmS2EwMG82QXF2VTJrVklURUpNZHBFT1BYVm4vdUVmd3luZy96c2JQK1FKb1ppYUxGT0JSRnZIejRiMFE2M2NhCnI3dHlGYjNpcjF4TnFlTXUzSFdEVEtSTVNtMzBDcTNmbXB0NG5NVUNnWUJSalhzak1mc1ZQTlNjVlozWncvanEKcTBYSHAzU3EvV1M4d2NpQnVBb2dNbUxGNHNtN29ZdTNqU2s1emUrMzVVK1FDdDhoaHNML2F5NHJpcHIwa2plRAo1ME1qRlVZcTZOeFJXUjY0YTRNaFNCUVpEaHNmWkZDekh4eGVHR2F0K0FabUpWTS93UkRYZnkrSEZmWHMvcXM0CjgraWpSTWJQR2xwUG5CL2NteitBblFLQmdRRENWbFBIck1uQy9Td21EbnhmajQ3MkpncjBPM0pOUkdRRS9BUDIKTFNud3VNUTBqbmw2MS9FNmlPV3dBUUExKzZITGR4eG50S0pROXpLYWZ2RnE3RlUwYS9EWFpiYWtqWU1wRnQxZApBeWNxbC92VS9wT21GZnJodG9xam1BMWRqbFg0dzZLYWpiWCtkUUhsNTdNZFRLQ0xNcVdhdC9tSEl6MFBJSmQ1CkdBdVRyUUtCZ0dBTFlWbEo4TDJqcE91M29VREJLaXl0NlVTaEdTNm15VHVSaGtKa2RjaklvYVM4NUxxZTh2QncKcit5NzUxU3pzcS9QUGU5K1JWSEdhR284MjdCTkpNenRRTGVjRU5BTmlZU2xQbEhQMkRzOWtMWi9iOS9IVE53RAo5ZnRNUFlKSDl6bkpySWNuZ3RFK0swbG80SkJBZnFQdXByUzFJVnk5MUkvQ0FNTk0yWHFyCi0tLS0tRU5EIFJTQSBQUklWQVRFIEtFWS0tLS0t",
            "public_key_sign": "LS0tLS1CRUdJTiBQVUJMSUMgS0VZLS0tLS0KTUlJQklqQU5CZ2txaGtpRzl3MEJBUUVGQUFPQ0FROEFNSUlCQ2dLQ0FRRUFxSkdhcTh3Z0FsMHdWOE9FVlFYVwo2VWNHQlMwU1ZGcUhkVk1iVXA1elhSV0VXOUVJaEZ5aTBER1J5NGt2NlpiWUFsaEJRMmxtYkpUeS9nVzMwRkhYCkdGU3h3M2NLNlBxTUhueEtSUENxMzVqV3Zad0E2Y2RCTGgxNTdjQmg4bC9nN2R2MlRUaGgwWlNVSWFmM2ZmcW0KTlBhOEV3TE96UXNSOXVEN2dMaHJTaTFVQWprSzI2UmNKOWJIVmpudjZ4aTM5NUJmRjJsMDJSVXoxZXJRR0ZJNAo4eHRUZlRIdlBCcitwVjRJTTJxU3RxbFRsR3EvVktEUi96eVIvUDByQTc5Sk9ibEdXNHJ5SkJDM1FibWFWKzVpCjFRSlBQVjV0YWNoM0FmMEhwbkREUWV6VHVFNFNYRUpCUWFudlNLeG9BMjZkeTVyVW15TEhOQU9ZY3UvanJlSUUKSHdJREFRQUIKLS0tLS1FTkQgUFVCTElDIEtFWS0tLS0t"
        }
    ]

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
                for key_pair in decryption_keys:
                    try:
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
                            private_key_encrypt=base64.b64decode(key_pair["private_key_encrypt"].encode("utf-8")),
                            public_key_sign=base64.b64decode(key_pair["public_key_sign"].encode("utf-8"))
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

def read_file(file_path: str):
    """
    Читает содержимое файла в зависимости от его типа.

    :param file_path: Путь к файлу.
    :return: Кортеж (содержимое файла, MIME-тип).
    """
    mime_type, _ = mimetypes.guess_type(file_path)
    if mime_type is None:
        mime_type = "application/octet-stream"  # Если тип не удалось определить

    try:
        if mime_type.startswith("text/"):
            # Если файл текстовый
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
        else:
            # Если файл бинарный
            with open(file_path, "rb") as f:
                content = f.read()
    except Exception as e:
        raise ValueError(f"Failed to read file {file_path}: {e}")

    return content, mime_type

# API для отправки письма на указанную почту
@app.post("/emails/send/", response_model=SendEmailResponse)
async def send_email(
    to_email: str = Form(...),
    subject: str = Form(...),
    body: str = Form(...),
    from_name: Optional[str] = Form(None),
    to_name: Optional[str] = Form(None),
    attachments: Optional[List[UploadFile]] = File(None),
    private_key_sign: Optional[str] = Form(None),
    public_key_encrypt: Optional[str] = Form(None),
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

        # Декодируем ключи из Base64 в байты
        if private_key_sign:
            private_key_sign = base64.b64decode(private_key_sign)
        if public_key_encrypt:
            public_key_encrypt = base64.b64decode(public_key_encrypt)

        # Проверяем, нужно ли шифрование
        if private_key_sign and public_key_encrypt:
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
        elif private_key_sign or public_key_encrypt:
            raise HTTPException(
                status_code=400,
                detail="Both private_key_sign and public_key_encrypt are required for encryption.",
            )

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
    uvicorn.run(app, host="0.0.0.0", port=8001)