import os.path
import json
import re
from contextlib import asynccontextmanager

import base64
from datetime import datetime
from io import BytesIO

import grpc
import uvicorn
from fastapi import FastAPI, HTTPException, Form, UploadFile, File
from pydantic import BaseModel
from typing import List, Optional

from starlette.responses import JSONResponse

from DB.RSAKeyDatabase import RSAKeyDatabase
from EProtocols.IMAPClient import IMAPClient  # Используем существующий IMAPClient
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from EProtocols.SMTPClient import SMTPClient
from SecureEmailClient import SecureEmailClient

from Models.models import *

# Использование lifespan для событий старта и остановки
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Инициализация при старте
    await db.connect()
    await db.create_tables()
    imap_client.open_connect()
    print("Приложение запущено!")
    yield
    # Очистка при завершении
    # Остановка IMAP-клиента при завершении работы сервера
    imap_client.close_connect()
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

# Allow all origins (for development)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins, change this to specific domains for production
    allow_credentials=True,
    allow_methods=["*"],  # Allows all HTTP methods (GET, POST, etc.)
    allow_headers=["*"],  # Allows all headers
)

# Инициализация IMAP-клиента
imap_client = IMAPClient("imap.mail.ru", "donntu_test@mail.ru", "wrixCgaMYsqXWmVbBPS7")

# Инициализация SMTP-клиента
smtp_client = SMTPClient("smtp.mail.ru", "donntu_test@mail.ru", "wrixCgaMYsqXWmVbBPS7")

db = RSAKeyDatabase()

@app.post("/change_imap_account/")
async def change_imap_account(request: ChangeAccountRequest):
    try:
        imap_client.change_account(
            new_email_user=request.email_user,
            new_email_pass=request.email_pass,
            new_imap_server=request.imap_server,
            new_port=request.port
        )
        return {"message": f"IMAP account changed to {request.email_user}"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error changing IMAP account: {str(e)}")

@app.post("/change_smtp_account/")
async def change_smtp_account(request: ChangeAccountRequest):
    try:
        smtp_client.change_account(
            new_email_user=request.email_user,
            new_email_pass=request.email_pass,
            new_smtp_server=request.smtp_server,
            new_port=request.port
        )
        return {"message": f"SMTP account changed to {request.email_user}"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error changing SMTP account: {str(e)}")

@app.get("/current_imap_account/")
async def current_imap_account():
    return {
        "imap_server": imap_client.imap_server,
        "email_user": imap_client.email_user,
        "port": imap_client.port
    }

@app.get("/current_smtp_account/")
async def current_smtp_account():
    return {
        "smtp_server": smtp_client.smtp_server,
        "email_user": smtp_client.email_user,
        "port": smtp_client.port
    }

@app.post("/emails/", response_model=FetchEmailsResponse)
async def fetch_emails(request: FetchEmailsRequest):
    """
    Fetch emails from a specified folder with optional pagination.

    Args:
        request (FetchEmailsRequest): Parameters in JSON format.

    Returns:
        FetchEmailsResponse: List of emails.
    """
    # Достаем параметры из запроса
    folder_name = request.folder_name
    offset = request.offset
    limit = request.limit

    try:
        # Пытаемся получить письма из IMAP
        emails = imap_client.fetch_emails(folder_name=folder_name, start=offset, limit=limit)
    except Exception as e:
        print(f"Failed to fetch emails from IMAP for folder {folder_name}: {e}")
        emails = None

    if emails:
        # Формируем список из IMAP
        emails_list = [
            SummaryEmailResponse(
                id=email["id"],
                sender=email["sender"],
                subject=email["subject"],
                date=email["date"]
            )
            for email in emails
        ]
    else:
        # Получаем данные из базы
        emails_list = await db.get_emails_summary_from_db(folder_name=folder_name, offset=offset, limit=limit)

    # Возвращаем результат
    return FetchEmailsResponse(emailsList=emails_list)

@app.post("/authorize_account/")
async def authorize_account(credentials: AccountCredentials):
    try:
        # Авторизация IMAP
        imap_client.change_account(
            new_email_user=credentials.email_user,
            new_email_pass=credentials.email_pass,
            new_imap_server=credentials.imap_server,
            new_port=credentials.imap_port
        )
        # Авторизация SMTP
        smtp_client.change_account(
            new_email_user=credentials.email_user,
            new_email_pass=credentials.email_pass,
            new_smtp_server=credentials.smtp_server,
            new_port=credentials.smtp_port
        )

        return {"message": "IMAP and SMTP accounts successfully authorized."}
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error during account authorization: {str(e)}")

# Глобальный массив для хранения вложений
global_attachments = []

global_keys_file = None

@app.get("/keys/export/")
async def export_public_keys():
    """
    Экспорт всех публичных ключей в файл и отправка его
    """
    global global_keys_file

    file_obj = await db.export_keys_to_file()

    # Генерируем временное имя файла
    temp_dir = "rsa_keys"
    file_name = "exported_public_keys.json"
    os.makedirs(temp_dir, exist_ok=True)
    file_path = os.path.join(temp_dir, file_name)

    # Сохраняем файл на диск (для последующего Models-запроса на скачивание)
    with open(file_path, "wb") as f:
        f.write(file_obj.read())

    # Добавляем файл в global_attachments
    global_keys_file = file_path

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path, filename=file_name)

@app.post("/keys/import/")
async def import_public_keys(file: UploadFile = File(...)):
    """
    Импорт публичных ключей из загруженного файла.
    """
    # Читаем файл в памяти
    file_content = await file.read()
    file_obj = BytesIO(file_content)

    try:
        result_message = await db.import_keys_from_file(file_obj)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON file format")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return {"message": result_message}

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

@app.post("/emails/info/", response_model=FetchEmailInfoResponse)
async def fetch_email_info(request: FetchEmailInfoRequest):
    """
    Models для получения информации о письме с декодированием Base64 и автоматическим дешифрованием.

    Args:
        request (FetchEmailInfoRequest): Параметры запроса с ID письма и именем папки.

    Returns:
        FetchEmailInfoResponse: Информация о письме.

    Raises:
        HTTPException: Ошибка, если письмо не найдено или ключи не подошли.
    """
    global global_attachments
    global_attachments.clear()  # Очищаем предыдущие вложения

    try:

        # Получаем параметры из тела запроса
        email_id = request.email_id
        folder_name = request.folder_name

        email_info = await db.get_email_from_db(email_id=email_id, folder_name=folder_name)

        if not email_info:
            try:
                # Получаем информацию о письме
                email_info = imap_client.fetch_email_info(email_uid=str(email_id).encode(), folder_name=folder_name)

                await db.add_letter(
                    folder_name=folder_name,
                    sender=extract_email(email_info["sender"]),
                    recipient=imap_client.email_user,
                    to_name=email_info["to"],
                    subject=email_info["subject"],
                    date=email_info["date"],
                    body=email_info.get("body"),
                    attachments=email_info.get("attachments", []),
                    letter_id=email_id,
                )

            except Exception as e:
                print(f"Failed to fetch email info from IMAP: {e}")
                email_info = None

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

                decryption_keys = await db.get_decrypt_keys(current_recipient_email=imap_client.email_user, sender_email=sender_email)

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

                        break

                    except grpc.RpcError as e:
                        # Обрабатываем ошибки gRPC
                        if e.code() == grpc.StatusCode.INVALID_ARGUMENT:
                            continue
                        else:
                            raise HTTPException(status_code=500, detail=f"Server error: {e.details()}")

                    except Exception as e:
                        raise HTTPException(status_code=400, detail=f"Failed to decrypt email: {e}")

            if not decrypted_body:
                # Если тело не является JSON, возвращаем как есть
                decrypted_body = encrypted_body
                decrypted_attachments = [{"filename": att["filename"], "content": att["content"]} for att in
                                         encrypted_attachments]

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
            sender=extract_email(email_info["sender"]),
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
    Models для загрузки вложения.

    Args:
        filename (str): Имя файла вложения.

    Returns:
        FileResponse: Файл вложения.
    """
    file_path = os.path.join("attachments", filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(file_path, filename=filename)

@app.post("/generate-keys/")
async def generate_and_send_keys(to_email: str = Form(...)):
    # Генерация новых ключей
    keys = secure_email_client.generate_keys()

    # Кодирование публичных ключей в BASE64
    keys_base64 = {
        "public_key_sign": base64.b64encode(keys["public_key_sign"]).decode(),
        "public_key_encrypt": base64.b64encode(keys["public_key_encrypt"]).decode()
    }

    current_date = db.get_current_date()

    # Формирование тела письма
    email_body_data = {
        "public_key_sign": keys_base64["public_key_sign"],
        "public_key_encrypt": keys_base64["public_key_encrypt"],
        "create_date":  current_date,
    }

    body = json.dumps(email_body_data, ensure_ascii=False)

    # test_inserts = {
    #     "sender_email": to_email,
    #     "current_recipient_email": imap_client.email_user,
    #     "private_key_sign": keys["private_key_sign"],  # Уже байты
    #     "private_key_encrypt": keys["private_key_encrypt"],  # Уже байты
    #     "public_key_sign": keys["public_key_sign"],  # Уже байты
    #     "public_key_encrypt": keys["public_key_encrypt"],  # Уже байты
    #     "create_date": current_date,
    # }

    await db.insert_private_keys(
        sender_email=to_email,
        current_recipient_email=imap_client.email_user,
        private_key_sign=keys["private_key_sign"],  # Уже байты
        private_key_encrypt=keys["private_key_encrypt"],  # Уже байты
        public_key_sign=keys["public_key_sign"],  # Уже байты
        public_key_encrypt=keys["public_key_encrypt"],  # Уже байты
        create_date=current_date
    )

    send_response = await send_email(
        to_email=to_email,
        subject=f"RSA_PUBLIC_KEYS <{current_date}>",
        body=body,
        from_name="Sender",
        to_name="Recipient",
        use_encrypt=False
    )

    # Возврат успешного ответа
    return {"message": "Keys generated and email sent successfully", "email_status": send_response}

@app.post("/emails/sent/", response_model=SendEmailResponse)
async def send_email(
    to_email: str = Form(...),
    subject: str = Form(...),
    body: str = Form(...),
    from_name: str = Form(None),
    to_name: str = Form(None),
    attachments: Optional[List[UploadFile]] = File(None),
    use_encrypt: Optional[bool] = Form(True)
):
    try:
        smtp_client.open_connect()

        # Преобразуем вложения в байтовый формат
        file_attachments = []
        if isinstance(attachments, list) and attachments:
            for file in attachments:
                if file is not None:
                    content = await file.read()
                    file_attachments.append({
                        "filename": file.filename,
                        "content": content,
                    })

        # Проверяем, нужно ли шифрование
        if use_encrypt:
            encrypt_keys = await db.get_encrypt_sign_keys(
                current_sender_email=smtp_client.email_user,
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
        message = smtp_client.send_email(
            to_email=to_email,
            subject=subject,
            body=body,
            from_name=from_name,
            to_name=to_name,
            attachments=file_attachments,
        )
        smtp_client.close_connect()

        imap_client.save_to_sent_folder(message.as_string())

        return SendEmailResponse(message="Email successfully sent.")
    except Exception as e:
        print(f"Error during email sending: {e}")
        smtp_client.close_connect()
        raise HTTPException(status_code=500, detail=f"Failed to send email: {e}")

@app.get("/folders/", response_model=List[dict])
async def get_folders():
    """
    Models для получения списка папок на IMAP-сервере.
    """
    try:
        if not imap_client.is_connection_active():
            imap_client.open_connect()

        folders = imap_client.get_folders()
        if isinstance(folders, dict) and "error" in folders:
            raise HTTPException(status_code=500, detail=folders["error"])

        return folders
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Ошибка сервера: {str(e)}")

@app.put("/sync-public-keys/")
async def sync_public_keys(
    recipient_email: str,
):
    try:
        # Получаем дату последней записи
        last_date = await db.get_last_insert_public_keys_date(imap_client.email_user, recipient_email)
        last_date_str = last_date.isoformat() if last_date else "1970-01-01T00:00:00"

        # Запрашиваем письма с ключами в формате JSON
        emails_data = imap_client.fetch_keys_emails_as_json()
        if not emails_data:
            return JSONResponse({"status": "No valid emails found."})

        # Отбираем только новые ключи
        new_keys = [
            email_data
            for email_data in emails_data
            if datetime.fromisoformat(email_data["create_date"]) > last_date
        ]

        if not new_keys:
            return {"status": "No new keys to add."}

        # Добавляем новые ключи в базу данных
        for key_data in new_keys:
            await db.insert_public_keys(
                current_sender_email=imap_client.email_user,
                recipient_email=recipient_email,
                public_key_sign=base64.b64decode(key_data["public_key_sign"]),
                public_key_encrypt=base64.b64decode(key_data["public_key_encrypt"]),
                create_date=key_data["create_date"]
            )

        return {"status": "Success", "new_keys_added": len(new_keys)}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/email/move_to_trash")
async def move_to_trash(
        email_id: str = Form(...),
        folder_name: str = Form("Inbox")
):
    """
    Перемещает письмо в корзину в БД и удаляет его с IMAP сервера.

    Args:
        request (MoveToTrashRequest): Параметры запроса.
        db (RSAKeyDatabase): Инстанс базы данных.
        imap_client (IMAPClient): Инстанс IMAP клиента.

    Raises:
        HTTPException: Если произошла ошибка на этапе перемещения или удаления.

    Returns:
        dict: Ответ с результатом операции.
    """
    trash_folder = "Trash"  # Название папки "Удаленные" в вашей БД

    try:

        # Удаление письма с IMAP-сервера
        imap_client.delete_email(email_uid=email_id, folder_name=folder_name)

        # Перемещение письма в "Trash" в базе данных
        await db.move_letter(letter_id=email_id, source_folder_name=folder_name, target_folder_name=trash_folder)

        return {"message": f"Письмо с ID {email_id} перемещено в корзину и удалено с сервера."}

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Произошла ошибка: {e}")


@app.post("/email/delete_from_trash")
async def delete_from_trash(
        email_id: int = Form(...)
):
    """
    Удаляет письмо из корзины окончательно (из БД и IMAP сервера).

    Args:
        request (DeleteFromTrashRequest): Параметры запроса.
        db (RSAKeyDatabase): Инстанс базы данных.
        imap_client (IMAPClient): Инстанс IMAP клиента.

    Raises:
        HTTPException: Если произошла ошибка на этапе удаления.

    Returns:
        dict: Ответ с результатом операции.
    """
    trash_folder = "Trash"  # Название папки "Корзина" в вашей базе данных

    try:

        # Удаление письма из базы данных
        await db.delete_letter(letter_id=email_id, folder_name=trash_folder)

        return {"message": f"Письмо с ID {email_id} успешно удалено из корзины."}

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Произошла ошибка: {e}")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)