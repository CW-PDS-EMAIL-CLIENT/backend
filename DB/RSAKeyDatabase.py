import io
import json
from datetime import datetime
from typing import Optional, List, Dict

from databases import Database
from fastapi import HTTPException
from sqlalchemy import Exists

from Models.models import SummaryEmailResponse

DATABASE_URL = "sqlite:///rsa_keys.db"

class RSAKeyDatabase:
    def __init__(self, database_url=DATABASE_URL):
        self.database = Database(database_url)

    async def connect(self):
        """Открыть подключение к базе данных."""
        await self.database.connect()

    async def disconnect(self):
        """Закрыть подключение к базе данных."""
        await self.database.disconnect()

    async def create_tables(self):
        """Создает таблицы с уникальными ограничениями для ключей и email-адресов."""
        # Создаем таблицу Emails
        await self.database.execute("""
        CREATE TABLE IF NOT EXISTS Emails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL
        )
        """)

        # Создаем таблицу PrivateRSAKeys
        await self.database.execute("""
        CREATE TABLE IF NOT EXISTS PrivateRSAKeys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sender_email_id INTEGER NOT NULL,
            current_recipient_email_id INTEGER NOT NULL,
            private_key_sign BLOB NOT NULL,
            public_key_sign BLOB NOT NULL,
            private_key_encrypt BLOB NOT NULL,
            public_key_encrypt BLOB NOT NULL,
            create_date DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
            UNIQUE (sender_email_id, current_recipient_email_id, private_key_sign, private_key_encrypt),
            FOREIGN KEY (sender_email_id) REFERENCES Emails (id) 
                ON DELETE CASCADE 
                ON UPDATE CASCADE,
            FOREIGN KEY (current_recipient_email_id) REFERENCES Emails (id) 
                ON DELETE CASCADE 
                ON UPDATE CASCADE
        )
        """)

        # Создаем таблицу PublicRSAKeys
        await self.database.execute("""
        CREATE TABLE IF NOT EXISTS PublicRSAKeys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            current_sender_email_id INTEGER NOT NULL,
            recipient_email_id INTEGER NOT NULL,
            public_key_sign BLOB NOT NULL,
            public_key_encrypt BLOB NOT NULL,
            create_date DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
            UNIQUE (current_sender_email_id, recipient_email_id, public_key_sign, public_key_encrypt),
            FOREIGN KEY (current_sender_email_id) REFERENCES Emails (id) 
                ON DELETE CASCADE 
                ON UPDATE CASCADE,
            FOREIGN KEY (recipient_email_id) REFERENCES Emails (id) 
                ON DELETE CASCADE 
                ON UPDATE CASCADE
        )
        """)

        # Создаем таблицу Folders
        await self.database.execute("""
        CREATE TABLE IF NOT EXISTS Folders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE -- Имя папки
        )
        """)

        # Создаем таблицу Letters
        await self.database.execute("""
        CREATE TABLE IF NOT EXISTS Letters (
            id INTEGER NOT NULL,
            folder_id INTEGER NOT NULL,
            sender_id INTEGER NOT NULL,
            recipient_id INTEGER NOT NULL,
            to_name TEXT NOT NULL,
            subject TEXT NOT NULL,
            date DATETIME NOT NULL,
            body BLOB NOT NULL,
            PRIMARY KEY (id, folder_id),
            FOREIGN KEY (folder_id) REFERENCES Folders (id) 
                ON DELETE CASCADE ON UPDATE CASCADE,
            FOREIGN KEY (sender_id) REFERENCES Emails (id) 
                ON DELETE CASCADE ON UPDATE CASCADE,
            FOREIGN KEY (recipient_id) REFERENCES Emails (id) 
                ON DELETE CASCADE ON UPDATE CASCADE
        )
        """)

        # Создаем таблицу Files
        await self.database.execute("""
        CREATE TABLE IF NOT EXISTS Files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            letter_id INTEGER NOT NULL,
            folder_id INTEGER NOT NULL,
            file_name TEXT NOT NULL,
            file_data BLOB NOT NULL,
            FOREIGN KEY (letter_id, folder_id) REFERENCES Letters (id, folder_id) 
                ON DELETE CASCADE
        )
        """)

    async def insert_email(self, email: str) -> int:
        """Вставляет email в таблицу Emails и возвращает ID."""
        query = "INSERT OR IGNORE INTO Emails (email) VALUES (:email)"
        await self.database.execute(query, {"email": email})

        select_query = "SELECT id FROM Emails WHERE email = :email"
        row = await self.database.fetch_one(select_query, {"email": email})
        if row:
            return row["id"]
        raise HTTPException(status_code=500, detail="Не удалось вставить email.")

    async def insert_private_keys(
            self,
            sender_email: str,
            current_recipient_email: str,
            private_key_sign: bytes,
            public_key_sign: bytes,
            private_key_encrypt: bytes,
            public_key_encrypt: bytes,
            create_date: str = None
    ):
        """Вставляет приватные RSA-ключи для указанных email-адресов."""
        sender_id = await self.insert_email(sender_email)
        recipient_id = await self.insert_email(current_recipient_email)

        if not create_date:
            create_date = self.get_current_date()

        query = """
        INSERT INTO PrivateRSAKeys (
            sender_email_id, current_recipient_email_id, 
            private_key_sign, public_key_sign, 
            private_key_encrypt, public_key_encrypt, 
            create_date
        ) 
        VALUES (
            :sender_id, :recipient_id, 
            :private_key_sign, :public_key_sign, 
            :private_key_encrypt, :public_key_encrypt, 
            :create_date
        )
        """
        return await self.database.execute(query, {
            "sender_id": sender_id,
            "recipient_id": recipient_id,
            "private_key_sign": private_key_sign,
            "public_key_sign": public_key_sign,
            "private_key_encrypt": private_key_encrypt,
            "public_key_encrypt": public_key_encrypt,
            "create_date": create_date,
        })

    async def insert_public_keys(
            self,
            current_sender_email: str,
            recipient_email: str,
            public_key_sign: bytes,
            public_key_encrypt: bytes,
            create_date: str = None
    ):
        """Вставляет публичные RSA-ключи для отправителя и получателя."""
        sender_id = await self.insert_email(current_sender_email)
        recipient_id = await self.insert_email(recipient_email)

        if not create_date:
            create_date = self.get_current_date()

        query = """
        INSERT INTO PublicRSAKeys (
            current_sender_email_id, recipient_email_id, 
            public_key_sign, public_key_encrypt, 
            create_date
        ) 
        VALUES (
            :sender_id, :recipient_id, 
            :public_key_sign, :public_key_encrypt, 
            :create_date
        )
        """
        return await self.database.execute(query, {
            "sender_id": sender_id,
            "recipient_id": recipient_id,
            "public_key_sign": public_key_sign,
            "public_key_encrypt": public_key_encrypt,
            "create_date": create_date,
        })

    async def get_current_public_keys(
            self, current_sender_email: str, recipient_email: str, date_limit: str = None
    ):
        """Получает публичные ключи для указанных отправителя и получателя из PrivateRSAKeys."""
        if not date_limit:
            date_limit = self.get_current_date()

        query = """
        SELECT prk.public_key_sign, prk.public_key_encrypt
        FROM PrivateRSAKeys prk
        JOIN Emails sender ON prk.sender_email_id = sender.id
        JOIN Emails recipient ON prk.current_recipient_email_id = recipient.id
        WHERE 
            sender.email = :sender_email 
            AND recipient.email = :recipient_email 
            AND prk.create_date <= :date_limit
        ORDER BY prk.create_date DESC
        """
        rows = await self.database.fetch_all(query, {
            "sender_email": current_sender_email,
            "recipient_email": recipient_email,
            "date_limit": date_limit
        })
        return [{"public_key_sign": row["public_key_sign"], "public_key_encrypt": row["public_key_encrypt"]} for row in
                rows]

    async def get_decrypt_keys(
            self, current_recipient_email: str, sender_email: str, date_limit: str = None
    ):
        """Получает приватный ключ получателя и публичный ключ подписи отправителя."""
        if not date_limit:
            date_limit = self.get_current_date()

        query = """
        SELECT 
            prk.private_key_encrypt AS recipient_private_key_encrypt,
            pub.public_key_sign AS sender_public_key_sign
        FROM PublicRSAKeys pub
        JOIN Emails sender ON pub.current_sender_email_id = sender.id
        JOIN Emails recipient ON pub.recipient_email_id = recipient.id
        JOIN PrivateRSAKeys prk ON prk.current_recipient_email_id = recipient.id
        WHERE 
            sender.email = :sender_email 
            AND recipient.email = :recipient_email 
            AND pub.create_date <= :date_limit
            AND prk.create_date <= :date_limit
        ORDER BY pub.create_date DESC
        """
        rows = await self.database.fetch_all(query, {
            "sender_email": sender_email,
            "recipient_email": current_recipient_email,
            "date_limit": date_limit
        })

        if rows:
            return [
                {
                    "private_key_encrypt": row["recipient_private_key_encrypt"],
                    "public_key_sign": row["sender_public_key_sign"],
                }
                for row in rows
            ]

        raise HTTPException(status_code=404, detail="Для этой почты не было найдено ключей.")

    async def get_encrypt_sign_keys(
            self, current_sender_email: str, recipient_email: str, date_limit: str = None
    ):
        """
        Получает публичный ключ для шифрования получателя и приватный ключ для подписи отправителя.
        """
        if not date_limit:
            date_limit = self.get_current_date()

        query = """
        SELECT 
            pub.public_key_encrypt AS recipient_public_key_encrypt,
            prk.private_key_sign AS sender_private_key_sign
        FROM PublicRSAKeys pub
        JOIN Emails sender ON pub.current_sender_email_id = sender.id
        JOIN Emails recipient ON pub.recipient_email_id = recipient.id
        JOIN PrivateRSAKeys prk ON prk.sender_email_id = sender.id
        WHERE 
            sender.email = :sender_email 
            AND recipient.email = :recipient_email 
            AND pub.create_date <= :date_limit
            AND prk.create_date <= :date_limit
        ORDER BY pub.create_date DESC
        LIMIT 1
        """
        row = await self.database.fetch_one(query, {
            "sender_email": current_sender_email,
            "recipient_email": recipient_email,
            "date_limit": date_limit
        })

        if row:
            return {
                "public_key_encrypt": row["recipient_public_key_encrypt"],
                "private_key_sign": row["sender_private_key_sign"],
            }

        raise HTTPException(status_code=404, detail="Для этой почты не было найдено ключей.")

    async def get_last_insert_public_keys_date(self, sender_email, recipient_email):
        """Возвращает последнюю дату добавления публичного ключа для указанных email адрессов"""

        query = """
        SELECT 
            pub.create_date AS last_create_date
        FROM PublicRSAKeys pub
        JOIN Emails sender ON pub.current_sender_email_id = sender.id
        JOIN Emails recipient ON pub.recipient_email_id = recipient.id
        WHERE 
            sender.email = :sender_email 
            AND recipient.email = :recipient_email 
        ORDER BY pub.create_date DESC
        LIMIT 1
        """

        row = await self.database.fetch_one(query, {
            "sender_email": sender_email,
            "recipient_email": recipient_email
        })

        return datetime.fromisoformat(row["last_create_date"]) if row else None

    async def get_emails(self):
        """Возвращает список всех email из таблицы Emails."""
        query = "SELECT email FROM Emails"
        rows = await self.database.fetch_all(query)
        return [row["email"] for row in rows] if rows else []

    def get_current_date(self):
        """Возвращает текущую дату и время."""
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    async def export_keys_to_file(self):
        """Экспорт всех ключей в JSON-файл с использованием email-адресов и возврат файла в памяти."""
        # Получение публичных ключей
        public_query = """
        SELECT 
            pub.create_date, 
            sender.email AS sender_email, 
            recipient.email AS recipient_email, 
            pub.public_key_encrypt AS public_key_encrypt, 
            pub.public_key_sign AS public_key_sign
        FROM PublicRSAKeys pub
        JOIN Emails sender ON pub.current_sender_email_id = sender.id
        JOIN Emails recipient ON pub.recipient_email_id = recipient.id
        """
        public_rows = await self.database.fetch_all(public_query)
        public_keys = [
            {key: (value.decode("utf-8") if isinstance(value, bytes) else value)
             for key, value in dict(row).items()}
            for row in public_rows
        ]

        # Получение приватных ключей
        private_query = """
        SELECT 
            priv.create_date, 
            sender.email AS sender_email, 
            recipient.email AS recipient_email, 
            priv.private_key_encrypt AS private_key_encrypt, 
            priv.private_key_sign AS private_key_sign,
            priv.public_key_encrypt AS public_key_encrypt,
            priv.public_key_sign AS public_key_sign
        FROM PrivateRSAKeys priv
        JOIN Emails sender ON priv.sender_email_id = sender.id
        JOIN Emails recipient ON priv.current_recipient_email_id = recipient.id
        """
        private_rows = await self.database.fetch_all(private_query)
        private_keys = [
            {key: (value.decode("utf-8") if isinstance(value, bytes) else value)
             for key, value in dict(row).items()}
            for row in private_rows
        ]

        # Формируем JSON с двумя массивами
        data = {
            "public_keys": public_keys,
            "private_keys": private_keys,
        }

        # Создаем JSON-строку и записываем ее в BytesIO
        file_obj = io.BytesIO()
        json_data = json.dumps(data, ensure_ascii=False, indent=4)
        file_obj.write(json_data.encode("utf-8"))  # Кодируем строку в байты
        file_obj.seek(0)  # Сбрасываем указатель на начало файла

        return file_obj

    async def import_keys_from_file(self, file_obj):
        """Импорт ключей из JSON-файла с использованием email-адресов."""
        # Загружаем содержимое файла
        file_obj.seek(0)
        data = json.load(file_obj)

        added_public_count = 0
        added_private_count = 0

        # Импорт публичных ключей
        for key in data.get("public_keys", []):
            try:
                await self.insert_public_keys(
                    current_sender_email=key["sender_email"],
                    recipient_email=key["recipient_email"],
                    public_key_sign=key["public_key_sign"].encode("utf-8") if key.get("public_key_sign") else None,
                    public_key_encrypt=key["public_key_encrypt"].encode("utf-8") if key.get(
                        "public_key_encrypt") else None,
                    create_date=key.get("create_date"),
                )
                added_public_count += 1
            except Exception as e:
                print(f"Ошибка при добавлении публичного ключа: {e}")

        # Импорт приватных ключей
        for key in data.get("private_keys", []):
            try:
                await self.insert_private_keys(
                    sender_email=key["sender_email"],
                    current_recipient_email=key["recipient_email"],
                    private_key_sign=key["private_key_sign"].encode("utf-8") if key.get("private_key_sign") else None,
                    public_key_sign=key["public_key_sign"].encode("utf-8") if key.get("public_key_sign") else None,
                    private_key_encrypt=key["private_key_encrypt"].encode("utf-8") if key.get(
                        "private_key_encrypt") else None,
                    public_key_encrypt=key["public_key_encrypt"].encode("utf-8") if key.get(
                        "public_key_encrypt") else None,
                    create_date=key.get("create_date"),
                )
                added_private_count += 1
            except Exception as e:
                print(f"Ошибка при добавлении приватного ключа: {e}")

        return f"Импортировано {added_public_count} публичных ключей и {added_private_count} приватных ключей."

    async def add_letter(
            self,
            folder_name: str,
            sender: str,
            recipient: str,
            to_name: str,
            subject: str,
            date: datetime,
            body: bytes,
            attachments: List[Dict[str, bytes]],
            letter_id: int,  # ID письма теперь обязательное
    ):
        """Добавляет новое письмо в указанную папку с обязательными параметрами ID письма и папки."""

        # Получаем или создаём папку
        folder_query = "SELECT id FROM Folders WHERE name = :name"
        folder = await self.database.fetch_one(folder_query, {"name": folder_name})
        if not folder:
            folder_insert = "INSERT INTO Folders (name) VALUES (:name)"
            await self.database.execute(folder_insert, {"name": folder_name})
            folder = await self.database.fetch_one(folder_query, {"name": folder_name})

        folder_id = folder["id"]

        # Получаем ID отправителя и получателя
        sender_id = await self.insert_email(sender)
        recipient_id = await self.insert_email(recipient)

        # Проверяем, нет ли письма с таким ID в папке
        check_query = "SELECT 1 FROM Letters WHERE id = :id AND folder_id = :folder_id"
        existing_letter = await self.database.fetch_one(check_query, {"id": letter_id, "folder_id": folder_id})
        if existing_letter:
            # raise Exception("A letter with this ID already exists in the folder.")
            return None

        # Добавляем письмо
        insert_letter_query = """
        INSERT INTO Letters (id, folder_id, sender_id, recipient_id, to_name, subject, date, body)
        VALUES (:id, :folder_id, :sender_id, :recipient_id, :to_name, :subject, :date, :body)
        """
        await self.database.execute(
            insert_letter_query,
            {
                "id": letter_id,
                "folder_id": folder_id,
                "sender_id": sender_id,
                "recipient_id": recipient_id,
                "to_name": to_name,
                "subject": subject,
                "date": date,
                "body": body,
            },
        )

        # Добавляем вложения
        if attachments:
            insert_file_query = """
            INSERT INTO Files (letter_id, folder_id, file_name, file_data)
            VALUES (:letter_id, :folder_id, :file_name, :file_data)
            """
            for attachment in attachments:
                await self.database.execute(
                    insert_file_query,
                    {
                        "letter_id": letter_id,
                        "folder_id": folder_id,  # Указываем также folder_id для внешнего ключа
                        "file_name": attachment["filename"],
                        "file_data": attachment["content"],
                    },
                )

    async def get_email_from_db(self, email_id: int, folder_name: str) -> Optional[Dict]:
        """Получает письмо и вложения из базы данных по ID письма и имени папки."""
        # Получаем ID папки по имени
        folder_query = "SELECT id FROM Folders WHERE name = :folder_name"
        folder = await self.database.fetch_one(folder_query, {"folder_name": folder_name})
        if not folder:
            return None

        folder_id = folder["id"]

        # Получаем письмо из таблицы Letters
        query = """
        SELECT 
            l.id AS email_id,
            e1.email AS sender,
            e2.email AS recipient,
            l.to_name,
            l.subject,
            l.date,
            l.body
        FROM Letters l
        JOIN Emails e1 ON l.sender_id = e1.id
        JOIN Emails e2 ON l.recipient_id = e2.id
        WHERE l.id = :email_id AND l.folder_id = :folder_id
        """
        letter = await self.database.fetch_one(query, {"email_id": email_id, "folder_id": folder_id})
        if not letter:
            return None

        # Получаем вложения из таблицы Files
        attachments_query = """
        SELECT file_name, file_data 
        FROM Files 
        WHERE letter_id = :email_id AND folder_id = :folder_id
        """
        attachments = await self.database.fetch_all(attachments_query, {"email_id": email_id, "folder_id": folder_id})

        # Возвращаем результат в виде словаря
        return {
            "id": letter["email_id"],
            "sender": letter["sender"],
            "recipient": letter["recipient"],
            "to": letter["to_name"],
            "subject": letter["subject"],
            "date": letter["date"],
            "body": letter["body"],
            "attachments": [
                {"filename": attachment["file_name"], "content": attachment["file_data"]} for attachment in attachments
            ],
        }

    async def add_or_get_folder_id(self, folder_name: str) -> int:
        """
        Добавляет папку в таблицу Folders, если её ещё нет, и возвращает её ID.
        Если папка уже существует, просто возвращает её ID.

        Args:
            folder_name (str): Название папки.

        Returns:
            int: ID папки.
        """
        query_select = """
        SELECT id FROM Folders WHERE name = :folder_name
        """
        query_insert = """
        INSERT INTO Folders (name) VALUES (:folder_name)
        """
        try:
            # Проверяем, существует ли папка
            result = await self.database.fetch_one(query_select, {"folder_name": folder_name})
            if result:
                return result["id"]

            # Если папки нет, добавляем её
            folder_id = await self.database.execute(query_insert, {"folder_name": folder_name})

            return folder_id
        except Exception as e:
            raise ValueError(f"Ошибка при добавлении или получении папки '{folder_name}': {e}")

    async def move_letter(self, letter_id: int, source_folder_name: str, target_folder_name: str):
        """
        Перемещает указанное письмо из одной папки в другую.

        Args:
            letter_id (int): ID письма.
            source_folder_name (str): Имя папки, из которой перемещается письмо.
            target_folder_name (str): Имя папки, в которую перемещается письмо.

        Raises:
            ValueError: Если письмо или папка не найдены.
        """
        # Получаем ID исходной папки
        source_folder_id = await self.database.fetch_val(
            "SELECT id FROM Folders WHERE name = :name",
            {"name": source_folder_name}
        )
        if not source_folder_id:
            raise ValueError(f"Source folder '{source_folder_name}' does not exist.")

        # Получаем ID целевой папки
        target_folder_id = await self.add_or_get_folder_id(target_folder_name)

        # Проверяем, что письмо существует в исходной папке
        letter_exists = await self.database.fetch_val(
            "SELECT 1 FROM Letters WHERE id = :letter_id AND folder_id = :folder_id",
            {"letter_id": letter_id, "folder_id": source_folder_id}
        )
        if not letter_exists:
            raise ValueError(f"Letter with ID {letter_id} does not exist in folder '{source_folder_name}'.")

        # Обновляем папку письма
        await self.database.execute(
            "UPDATE Letters SET folder_id = :target_folder_id WHERE id = :letter_id AND folder_id = :source_folder_id",
            {"target_folder_id": target_folder_id, "letter_id": letter_id, "source_folder_id": source_folder_id}
        )

    async def delete_letter(self, letter_id: int, folder_name: str):
        """
        Удаляет указанное письмо из указанной папки.

        Args:
            letter_id (int): ID письма.
            folder_name (str): Имя папки.

        Raises:
            ValueError: Если письмо или папка не найдены.
        """
        # Получаем ID папки
        folder_id = await self.database.fetch_val(
            "SELECT id FROM Folders WHERE name = :name",
            {"name": folder_name}
        )
        if not folder_id:
            raise ValueError(f"Folder '{folder_name}' does not exist.")

        # Удаляем письмо
        result = await self.database.execute(
            "DELETE FROM Letters WHERE id = :letter_id AND folder_id = :folder_id",
            {"letter_id": letter_id, "folder_id": folder_id}
        )
        if result == 0:
            raise ValueError(f"Letter with ID {letter_id} does not exist in folder '{folder_name}'.")

    async def get_emails_summary_from_db(self, folder_name: str, offset: int, limit: int) -> List[SummaryEmailResponse]:
        """
        Возвращает список краткой информации о письмах из указанной папки.

        Args:
            folder_name (str): Имя папки.
            offset (int): Смещение для пагинации.
            limit (int): Лимит количества возвращаемых писем.

        Returns:
            List[SummaryEmailResponse]: Список писем.
        """
        query = """
        SELECT 
            l.id AS letter_id,
            e.email AS sender_email,
            l.subject,
            l.date
        FROM Letters l
        INNER JOIN Folders f ON l.folder_id = f.id
        INNER JOIN Emails e ON l.sender_id = e.id
        WHERE f.name = :folder_name
        ORDER BY l.date DESC
        LIMIT :limit OFFSET :offset
        """
        rows = await self.database.fetch_all(query,
                                             values={"folder_name": folder_name, "offset": offset, "limit": limit})

        # Формируем список SummaryEmailResponse
        return [
            SummaryEmailResponse(
                id=row["letter_id"],
                sender=row["sender_email"],
                subject=row["subject"],
                date=row["date"].strftime("%Y-%m-%d %H:%M:%S") if isinstance(row["date"], datetime) else row["date"]
            )
            for row in rows
        ]

if __name__ == "__main__":

    import asyncio
    import base64

    async def insert_test_data(db, sender_email, recipient_email, keys_base64_str):
        current_date = db.get_current_date()

        # Генерация тестовых ключей
        private_key_sign = base64.b64decode(keys_base64_str["private_key_sign_base64_str"])
        public_key_sign = base64.b64decode(keys_base64_str["public_key_sign_base64_str"])
        private_key_encrypt = base64.b64decode(keys_base64_str["private_key_encrypt_base64_str"])
        public_key_encrypt = base64.b64decode(keys_base64_str["public_key_encrypt_base64_str"])

        # Вставка приватных ключей
        private_keys_id = await db.insert_private_keys(
            sender_email=sender_email,
            current_recipient_email=recipient_email,
            private_key_sign=private_key_sign,
            public_key_sign=public_key_sign,
            private_key_encrypt=private_key_encrypt,
            public_key_encrypt=public_key_encrypt,
            create_date=current_date,
        )
        print(f"Приватные ключи добавлены с ID: {private_keys_id}")

        # Вставка публичн   ых ключей
        public_keys_id = await db.insert_public_keys(
            current_sender_email=sender_email,
            recipient_email=recipient_email,
            public_key_sign=public_key_sign,
            public_key_encrypt=public_key_encrypt,
            create_date=current_date,
        )
        print(f"Публичные ключи добавлены с ID: {public_keys_id}")

        # Получение публичных ключей
        public_keys = await db.get_current_public_keys(
            current_sender_email=sender_email,
            recipient_email=recipient_email,
        )
        print(f"Публичные ключи для {sender_email} -> {recipient_email}:")
        for key in public_keys:
            print(
                f"Подпись: {key['public_key_sign']}, Шифрование: {key['public_key_encrypt']}"
            )

        # Получение приватного ключа для расшифровки и публичного ключа подписи
        decrypt_keys = await db.get_decrypt_keys(
            current_recipient_email=recipient_email,
            sender_email=sender_email,
        )
        print(f"Ключи для расшифровки и подписи ({recipient_email} -> {sender_email}):")
        for key in decrypt_keys:
            print(
                f"Приватный ключ для расшифровки: {key['private_key_encrypt']}, Публичный ключ подписи: {key['public_key_sign']}"
            )

        # Получение ключей для шифрования и подписи
        encrypt_sign_keys = await db.get_encrypt_sign_keys(
            current_sender_email=sender_email,
            recipient_email=recipient_email,
        )
        print(
            f"Ключи для шифрования и подписи ({sender_email} -> {recipient_email}): "
            f"Шифрование: {encrypt_sign_keys['public_key_encrypt']}, "
            f"Подпись: {encrypt_sign_keys['private_key_sign']}"
        )

        # Получение списка e-mail
        emails = await db.get_emails()
        print("Список e-mail:")
        for email in emails:
            print(email)

    async def main():
        # Инициализация базы данных
        db = RSAKeyDatabase("sqlite:/..//rsa_keys.db")
        await db.connect()
        await db.create_tables()

        keys_base64_str_one = {
            "private_key_sign_base64_str": b"LS0tLS1CRUdJTiBSU0EgUFJJVkFURSBLRVktLS0tLQpNSUlFb3dJQkFBS0NBUUVBMTZaWmgyeHlZQnBqYkJMMTBGbkl3VGZ2ZGU1OC9ERE5JVXhlOVMranlTQlY5UzBDCkVBWjQ2SXpUZDlzVEhXQWdSMHplZFRSbW9pQjNvQ3dKb01oMWhpTVczekVoUTVMSWh1OVhNeXlCVTd4WXQzeTgKSFJaOC9XclRQeURndHdKRVNwZW53VzhWZkZEUnBLRmowRGNLdjRUV3ZORW5aelRHYmQ5R3dMdkFsdWRIU1FIdgpzMFhmQzNKS2U3NGpQc1RyMU5xeWtXVEF5bjlqMGxjQm1jdWxvUWxSOUlWOGltTXFEcG4zSHp3YWJQSGh2cGI5ClFwN0Fpb1RLbml4Q1pmekt6engyR29yY3k4TW1mQUlJTGp6VlY4czlEanB0bDRwWW1jcUFCQ0U2TlNZQ1c1TXEKVzloY0MzRjhpcG5UUFBwTStXUU5TYjEzcEtkeUlWWkRWcXZ6dVFJREFRQUJBb0lCQUF3b0lncnExNlhJUnd1TQpKQlJiUTJCMUZVZzZLZ3lUZWJUalY4VU5xdmVISGFGbEtLVWJvRXhIeUJJTkpRNDJZWXR6YjJUL0Q3d2JCWE5mCm1DbGFzNWxjdUFqYi9hcVFCMExvRWl2ZDJlcU5CeGxNN0ZQZGRTMWFETStWdkdWRXVQSFZpOHp4Uks1TjVndVkKVjRhZzI3ZkJOdFBOSEtJS1RSZGJpMk1KRW9uUEpHckxnR3VJRTNUUjArZmduOThrRFV3UmprZkdqVGdINzVhUQpWdnA5M3RrSld2RVJNY0xVK2FTL3dSa09yUHhOZXNWZnpRcnUzbnQzKzh1cGFDaDczNHFKUUw0S05QWEwzRXhlClNjNmJscllSc0RSSFZKbkxzdklucjloTm5YYlhNQ2ExRjF3ZldPblUrbXVRL29SNFhIWERaQ1VNOGtjY2dPWEoKMDVheVkyc0NnWUVBNUl0ZGNnNnk3RGw3VTYyMnRUZW9FOHc0eTQ0Njc5V3IrUWl1aVdJTURBaS96VnJmejQ0WApHWldaYXJUZ2pZZUxxYzBqTlpOOXQzY2pUUFBhR2EzeDdBNDQwMzMzYWpyRkdyV3I0d2VmbHBGcHJ1UTgrWDJnCm5aNml1NTJtbzg2cUFiNTBXM05aK0dVYUoyRitvZ2NxMHFZUXdDMzQ1SVIwRVFLTFUzaXZuWHNDZ1lFQThZNXMKOEM0NUpZeWVRU1FmV2wxMHZzMlNMdnZtT05xeEpOWlg4dnNHT0VmS1RJeFZhYUczUXRVaUdMWG0yLzZmd3JYKwpuTmhtRG13bGdBdTdVb3RZeVpkckkzQ3UwV1I4REJyNGpjb01EbFFvN0xjcnBTYSs5ZHJiSVVtRWVrNHYyZEUrCjlJVGZNQjVjMjhyT00rcEJkK1JDcEk4cTdtRXRZbzRoTnRyNUcxc0NnWUEzTWtGN1RubC8rOUlCUDY4a3pUQlcKdDdmdjBZWUNib1IrUE02S2Q1ZVpRSE95VVFSRXlIaGp3WEd3QjhkRDV6eWY0ZDlqRFNBTHMwWmZTM1dkUmhscgpmWFBVQUZSRTM3VEM0cVdFeTA2THVzcmZabGdqbVdlMUtaNzcyUE5xRkh1U3VFQzU1WDRSTTduQlVSYVlZMHJBClhVTW1adlA1bk5PN1YvWDJUdXQ3Q1FLQmdRRHZoS0pRcGdUVVR0SzlGT3hoMWpsazJNSVRCSVFMN0EycTBUNzAKR0NUYXVaVEd3b0FPOWVPWnlXeTl3K0RlVTJSbTFiOWFGdGxiZzdETGZ0YUh5dFNIVURWVU51K2hnVm5mUnY4ZQoyVEdMSTdoUXdHL3VtclRQWSt2VTNla1d2V0NGUXc2QnR4NzN2Nk9qN1R6NkRWWk5ZM0VSYTBUT2lsMU9WRkJxCjdFWUY4UUtCZ0VtSTZPYS9kYlM1N2hwSUFPUWVyVWZTby9hb21VQ21TaENseUFhZFA2V0RSVzFlSWR2Q1Rtcm0KTmlOSjF2QlVzamdBRUw0U1hFdm5LNjV3cXNpdGtuVnJoYkdMalRQbVZNVFlJcFdRalR6UEpZSWtvNDk0NE1QegpFOUVkWU9LSE9kQ0RVRTUyYTd5bmlza09wSWMxSGZjU2F6TTMvSlBCakNBSlkrT3RTTzUvCi0tLS0tRU5EIFJTQSBQUklWQVRFIEtFWS0tLS0t",
            "public_key_sign_base64_str": b"LS0tLS1CRUdJTiBQVUJMSUMgS0VZLS0tLS0KTUlJQklqQU5CZ2txaGtpRzl3MEJBUUVGQUFPQ0FROEFNSUlCQ2dLQ0FRRUExNlpaaDJ4eVlCcGpiQkwxMEZuSQp3VGZ2ZGU1OC9ERE5JVXhlOVMranlTQlY5UzBDRUFaNDZJelRkOXNUSFdBZ1IwemVkVFJtb2lCM29Dd0pvTWgxCmhpTVczekVoUTVMSWh1OVhNeXlCVTd4WXQzeThIUlo4L1dyVFB5RGd0d0pFU3BlbndXOFZmRkRScEtGajBEY0sKdjRUV3ZORW5aelRHYmQ5R3dMdkFsdWRIU1FIdnMwWGZDM0pLZTc0alBzVHIxTnF5a1dUQXluOWowbGNCbWN1bApvUWxSOUlWOGltTXFEcG4zSHp3YWJQSGh2cGI5UXA3QWlvVEtuaXhDWmZ6S3p6eDJHb3JjeThNbWZBSUlManpWClY4czlEanB0bDRwWW1jcUFCQ0U2TlNZQ1c1TXFXOWhjQzNGOGlwblRQUHBNK1dRTlNiMTNwS2R5SVZaRFZxdnoKdVFJREFRQUIKLS0tLS1FTkQgUFVCTElDIEtFWS0tLS0t",
            "private_key_encrypt_base64_str": b"LS0tLS1CRUdJTiBSU0EgUFJJVkFURSBLRVktLS0tLQpNSUlFcEFJQkFBS0NBUUVBb2R6Z1dWWk10Z3A3OFZDeHZPZUlrZ2o4eG1KdTkxcm0yZFNpZFdKVElKMkNBZGFSCk1lVnMzT1lmTGd4L3BqOXVHVmR5T3hYTnByNlRqWDNoM3FBREFyakZTdkRwVlFDWS85RTgwV1NqQUY3VmtFZTAKOFdjdUJRT1Z5cDdqQnNEa0FEakdITm5YaWtUVnVFR2tBR3Y1dml0OUd0TjZPRGxNKzF3UGtIRWxUK3V1ODVaUgorVFU2aWM3SHI1RWdtM3E5cFdFRm1rSU1UN0NkNHZaeW03Y2hzUSt6Y3VYcnF3QmxyN0grNVRyNGtYZDF4VkQrCjcrRnpTWnljZ21PZjUzalZQTXZzZ1ZTUFJ6VkE5Z0hWcVdxUHoxUFNrcm9SN0tkZkdpaCthbUxnWFp3dU05UUsKSUFERjg4b0lhblhIT3JHS2wxelhVMnV0RytnSW9OMmZwdUF0bVFJREFRQUJBb0lCQUJQUXJXcGlaVHUzNXRwdwo3WUZadXQ5ZDJFd1ZDczZmUXptUmpWM2ZicHZFaklEYkdxVklGOTZuRVZRYTFabXRsRFhuL2FUOEUxUUJhcURjCnMwVUV3N21Xa3hpTWk1UUxZYStYbHVGdmQ0RDVHeDN4bVZZZ01vTU1vRTdReXF3dCt2dUg5OERhYmtlUUM3WGwKMjBUdDh3SHo0dm5ndjhxWVFUTllYdE5vOW85azhldXhqUDhMZFZvL3g0RTFabUpSVkJaeTY3ay9VWVhXeDFuMQpScXJWbTNtNWpjZW51YVpySzRicHNMeFZ6TlJ1emxWSTRQb0VPeis0aHdaTnhGSlJGSlZtUThNVFIzc2MwbS8yCjRzQk5adGNmYy90MGc2Lzk4cERUKzkxbURKQUdRTXVwTXdWTDNXWmsvY0tpdys2eXZmUVczUnVmejlNZDJRcDkKNUhwTWI0RUNnWUVBdlpvVnV3dXFiNjJVZDZZd2MwcnpTQ2gzUFRJVlBKQjZiSkhYM2VMU0xvQkgvSUF0RTc1Twpzc0FHMGhidFY5bDFkUHVRdUlJeVE5NUtINXVwZGsxVlZ2R2FIVDM3UHljV1dtYWNORlBYandQWEVmc2pJOGkxCmtuSmxROFlBSFV1WlRIK2RtWXZQR3Z1bU9nSU4yVXpucDhVWFdQaXJWRlBSdjBFM05uU0tZb2tDZ1lFQTJvdjMKVklIL0xsd01Ud3hBbjBpd1dqYW1wSERpZVB1N1oxQmx2NUpPK0tMaUZqQUltcmhPZDB3SlFIWG1kbzkrOXB0QgpCRUVKdTM5KzBReDdPQzUzbzN2RGg0M3F6QU5FRm82V3h5dmxyRUROL01ZbzUrOGR1Q1U5Z3VieS9SUEZwOHNQCkk1R0VjcFJCS0MxOGpsRWhJbU5WRHZxbGJ3NUxzaTV6R25rTDdwRUNnWUVBclVtNDlyMVF4c1ZFM3A0N3hnUUkKbWppeDBuS0Z5bGJhTFlTV1lTdS9vZFNJOXBSSG5yWGV3NnlTRDAzNUdzT2JnSkd6MFk3ZFZmNUNqT1QrV3l1UApCZW5IUzFhczNTbGlXcmxScHRuQ04rbndsWFNNeDFYWDdjTTBIbDlIRjM5UzJ3SUFEcWdqWDZ3RVh4d2xnQ2V6CnlqaHVnRmkyYmxvMVo3RzVQc0lCQU5FQ2dZQVVxVzcwdW1XWnlISVJkeU1VN0JaZ01SS0lNWFAzNURUUGk3WlMKNms0MUM1RThiOFlnZXBSUWl3dkU0R0N0ak51QURTV1VkV0dxTEYrYy9BVWFScXBnOW02Qi9sVFlmT2FQQzJRTgo2SVNLU0lZeEE3c1NVblVJMTl4ODU4REpWSGszWitkQ2dadDRDYlF2VEQyZVp1VXZEeDBYa1hMYWtRdHZDUjB3CnY0ajFRUUtCZ1FDdi90V1Z5aUVtb2RmZ2hGRDlPRTNWNUNReEc2V2g2YU1XL0JmaFZjbFY3ZmpPbnRJVEVjelQKeTJTTTVaYnM4L29hWlJ1ckJrVjFNRG9KbGE1RWV1UDVPYmJLdmEzQjhmUjFXOVlkeVI4eEd5R0pFZDBSeVRmYgpNTmdnUk1WbTVkeFhrYkg3eWFBZzFJWktTZEJpNGNCbm9yOFBPS0NNR2I2UExYUjMvMnFaaVE9PQotLS0tLUVORCBSU0EgUFJJVkFURSBLRVktLS0tLQ==",
            "public_key_encrypt_base64_str": b"LS0tLS1CRUdJTiBQVUJMSUMgS0VZLS0tLS0KTUlJQklqQU5CZ2txaGtpRzl3MEJBUUVGQUFPQ0FROEFNSUlCQ2dLQ0FRRUFvZHpnV1ZaTXRncDc4VkN4dk9lSQprZ2o4eG1KdTkxcm0yZFNpZFdKVElKMkNBZGFSTWVWczNPWWZMZ3gvcGo5dUdWZHlPeFhOcHI2VGpYM2gzcUFECkFyakZTdkRwVlFDWS85RTgwV1NqQUY3VmtFZTA4V2N1QlFPVnlwN2pCc0RrQURqR0hOblhpa1RWdUVHa0FHdjUKdml0OUd0TjZPRGxNKzF3UGtIRWxUK3V1ODVaUitUVTZpYzdIcjVFZ20zcTlwV0VGbWtJTVQ3Q2Q0dlp5bTdjaApzUSt6Y3VYcnF3QmxyN0grNVRyNGtYZDF4VkQrNytGelNaeWNnbU9mNTNqVlBNdnNnVlNQUnpWQTlnSFZxV3FQCnoxUFNrcm9SN0tkZkdpaCthbUxnWFp3dU05UUtJQURGODhvSWFuWEhPckdLbDF6WFUydXRHK2dJb04yZnB1QXQKbVFJREFRQUIKLS0tLS1FTkQgUFVCTElDIEtFWS0tLS0t",
        }

        keys_base64_str_two = {
            "private_key_sign_base64_str": b"LS0tLS1CRUdJTiBSU0EgUFJJVkFURSBLRVktLS0tLQpNSUlFb3dJQkFBS0NBUUVBNGh0YnVWK2cwdWpXZlNITW5BY09WL0pmUE0rS2xub1M2UkxVVXBMaTdoNUtkS1NXCkJFU0w0ZU9qMHJ2V3YvUWpJL1luMkhKd0g2VzhkS1N1OUZqYVpxTWpMT3ZCYWRCaTVBbzVLWnJ5S0lWQUFET0IKTUJxbFpkd0tnbDNuVGNSQlIzdlgzdlBVcE4zWURFZWNYOWdDd3FGc2tkalp1WUFpVENhYXhCSndhOEZnVU1iVAoyK2hyWVYwZTdvNzNTRHlCZU80Q01ZV294TkpPR09lMXZPWFIrNjROSFZhZFBaUHNXMFpIQzY4Wk16dFR5Rm11CmZrcDdsOXZPTWVpTDY0RmJsRWQrUDlabTEzUUhXNFc4OE5vUmpOSFRneEluRlRITS90MHFOL3pwMXowUVI2UksKWXpIeWJqZmZ2TzFHL3FVQ1U1c2t4UjBvMWFoMkkzRUh6U1YySFFJREFRQUJBb0lCQUFvMHhtL29iV08vejFqQQpJeEtDN2dhUndmTkdnZ0MzVzIycVpDdWpCanZONGJvQXFPWGg2emVEMVVRQXB4bXNqVDZGRUxqZ040ZnlMUDdOCjVUalIzdS9sbXNPZkU3Q3hUNWx3RGJML1U4RjQvRkhXQVZXWXlsRDkvUHB6L3lvZk92d2RUcm41WXlhYS9mTFYKODZ6TzNSY0lmdFJaaDhCc0ZJQS8rTm56WkNBMCtXVlAwUk93MjhqcklxeGZjL1N3ZmVVYlhDVURHK1FxSTBkUgpyUUZOdXlvMmFmdzQ2cFJJWU02cTFZRXdlMlQ5VTlIa01lNkxIL1pndkZmQUs3RHVtRlRLUmNPZnNJT245Z2hICjVndTRhbmYrZmM5eFJmZmRTSEQ1ekh1djBUcG1Tak9abWlGL0VXVnJNUzFzWTl4bU5FSkIwNktCMTVNMXkrRC8KbHRyTTZiRUNnWUVBNXYzUVJLTWVBYmEvT2IyVGUyL2xpWVk5UHdnUVBBSHcvT2xUeGI2L0FxL1hmWjAwTThaNwpJQ0sxVzFtRU9hU29EWHRZQkNWaWxJK3BoQXZjT1MwNkNUdDZlcDFLbWZBeEh4VHQ1UDR3SGd5a3dJRjFyMTVkCm1la1MrQmVNcnYxTUo4Q3A5dENXME10d28wWXVFWGxrWkZqdnBxR3kzY0E5Q2Z5SmVzc1NqaEVDZ1lFQStwWXAKc1BNQTd2ODhZWXVUaTVVbDFGblNRSlp6MnBqZEZPcUdXRHFxQy94VEtGdUVFTFFobUZ2OXRJdytWa1IxVGtsZQo0YnQ5TGUyQkNwd0tnczVaanU3a001dC9UaTZ0dms1QitFMTlDeHlUSG5wdW9jMkY5dlpiRzAyOGlyVHgxSEE4ClJSR3c0aDVObVdVeUVDMFdLQjVGMGdINGJKek1HVlRoWUVjV0MwMENnWUJ3M0hDbktKL2ZySCt3WVowdXdaU0EKWmxPRWVaY2RDc0hKZ09PS2lkRmdLYlI3VHBVVCt4VnJ0U214VVlLV2U0b1UxRUJEL2xRMVRDQkNRVjAvbm9adAp2bDd3aSt2SVhTQlRGSEhMNGhwMmhDejNWZ20vUHJjekhUdEVkcFVwWnQrUHlNWUNyeFlSUEdWemtUV3ZHZ1hnCk5jZ2FQWVZjYmJJbEwvdW9RSkozVVFLQmdBVWduM2ZFY1NkeXg0eURhNkIyaTlDZGllVFNiMHB3eUUxT1F6TjQKOTlQSTlQYWxjTDFhd2prNDRLY2FHNGh1WEN3ZTZqY2FQQVI5a0o5ajgvOGJNOC90NlhONDRoRDZlWW1rVmtzNwpZcXlnaUE0ZW1UYnNXcXBqL2hjLzd2U3pvU01rck1jSkJxS0oxakttVkhEcVMwTEU0ODdaUlhrTGVFMm9ZL2d4ClhDMGRBb0dCQUlaTTMxK1hNeXljdEhheGVBTkJHSWg2TVEyVDZUQlozVWVnTW5CYngwQTQ3RzZhYlZVL0p5WHcKeDBXa2xzbjVGT291bHErS1ZjdEM4TU5GekpLOHRnS0dSbW9ERjFCSU9XTGJGbGZ6OWxUQ3psNEhoeE9RSzVFZQpXT2tibzYycHdTUU1LcHZFUjFPS2pWaHpVMXZ1dzlkMG9PL1dTZUg5aU9lWGRPYUhxUVVaCi0tLS0tRU5EIFJTQSBQUklWQVRFIEtFWS0tLS0t",
            "public_key_sign_base64_str": b"LS0tLS1CRUdJTiBQVUJMSUMgS0VZLS0tLS0KTUlJQklqQU5CZ2txaGtpRzl3MEJBUUVGQUFPQ0FROEFNSUlCQ2dLQ0FRRUE0aHRidVYrZzB1aldmU0hNbkFjTwpWL0pmUE0rS2xub1M2UkxVVXBMaTdoNUtkS1NXQkVTTDRlT2owcnZXdi9RakkvWW4ySEp3SDZXOGRLU3U5RmphClpxTWpMT3ZCYWRCaTVBbzVLWnJ5S0lWQUFET0JNQnFsWmR3S2dsM25UY1JCUjN2WDN2UFVwTjNZREVlY1g5Z0MKd3FGc2tkalp1WUFpVENhYXhCSndhOEZnVU1iVDIraHJZVjBlN283M1NEeUJlTzRDTVlXb3hOSk9HT2Uxdk9YUgorNjROSFZhZFBaUHNXMFpIQzY4Wk16dFR5Rm11ZmtwN2w5dk9NZWlMNjRGYmxFZCtQOVptMTNRSFc0Vzg4Tm9SCmpOSFRneEluRlRITS90MHFOL3pwMXowUVI2UktZekh5YmpmZnZPMUcvcVVDVTVza3hSMG8xYWgySTNFSHpTVjIKSFFJREFRQUIKLS0tLS1FTkQgUFVCTElDIEtFWS0tLS0t",
            "private_key_encrypt_base64_str": b"LS0tLS1CRUdJTiBSU0EgUFJJVkFURSBLRVktLS0tLQpNSUlFcEFJQkFBS0NBUUVBcHNVMnp6OENoNlpQS1JaaWs0UGxUOTgwUUxuc2lEUjgyaTIrUXNXVnFxcG9UU3dOCnNLMmdDV2hxUkxMUFlxOFVqZFl6Zmo3MHVQMVFyQXkwTmx6L3BYMTJPNGRJT2VkeG12NU1tS0YrMGxGd1g1cEsKNGhNbnhVeG5BcUVRTVh0WjlDU3JzWmRCekY4VjBBcFg4UzkzbjJpNnJGZ254bWRQOHpLSUJtZ0orYzRPaitITQpwMytNRHhRa2MvTkEwWmluTmJiekFMQzhZT0Q5SjZUQm45dWdIMncwTlN4RTFLU2hsVDhEdlpyUktia3U3MUxUClRkdjVQYWhML1FHMlJIVytoMTRsYzF2ZEh4ZFg3VXBMeGtjeGluQytCRkdDQXBsR1RFV1h3c0ZzY3dDOExYK2cKOGxybzB3d0Q1aWh1S0lSQ050cEZldVFXcWJqTHgvL0hiN3RBY3dJREFRQUJBb0lCQUJMaVVBT0ZzZ2FrT1dDQQpyV2JnejQyTXk4RHNqTEVicUd1WU5Hd2hMWUpteTJxNXEwOHZTZWptenVtNmlhczJBaERSaVlFcEpkTHd0RHJYCk1XemFlUVJIUWFVWiszNjdDMjB1a0lQVC9hVlpIVzFsN2tiTlBucWozU0k2RkxoVnJHanQ0aGM0OW5WcTZ2QmsKeTNKL0duK05mMTNXbWFKb3ZtL2ViL0t4d3pkckE4M2NydnBheGpaQnRMNVdkSFlYaDAxZ1hqOTF6aTU0aUNkdgorWTU5Ym5uL3dBa1I4bXN5SmYwT2EvYjJGUDVnL3VUUmRBK3l6b0tHSUN6SVZLaW9kclRWQ0pLODhlanNOQXpKCkV1N2xZSkdGalZzZnhySnBlcVJ5QktuNTRaS3FCQm1WVkxUS0FuQkZpRnluWG1ZVjA2TUgvUkQ2MzBrRHUrcnEKeFBmeWwza0NnWUVBdTVqSkt2UUt3ODFEZk9rcmNKaklSS3gydUF1QUlKSndoUkhEK0tZWDA0U0tTbjcvbDc2bgpDVmFtc28zQXBrUXozWEZhUFcyWW50dFZidEJCSElQcmh6Q1FaNzlxT1BjK0ZrSXUwT3NtNG9UNzllU0NZZFY3CkhaU1pablRtTWhwenlKKzZjVWp6UjlUdXU5dUJkb0hFTWVFakh1SWtjUmVxSzJBMEN5OEVFRVVDZ1lFQTQ1UmkKWkIrQ0piMzR0SUxvanNOSXV2UlhDNnN4VDVmNm0xZVcvekE4VEIvY0EwZWx6OGplOUl6MUUvb0FVbzFIVVgrZAphakt1SmN5NVhUSDZlSWc4c0lRSnJxdVQ3UVJxcVRwVlZ5LzZOVk1qZWl4Q0FZQ1BLeG13Z0R1V3U2ZThGUDZ5CmxSekZoV0sxTHRwRFBGR1I4NGowdVZqQ1piaVcyenYrN3JKYzVWY0NnWUJET2tldFN2T29vNkN4M09XaVhqNDIKemc5bGVVbWJZcDlNTU1lb0RlMnY4V21WdE5sbnlmMFdUYVZEaTZVa2NJQ2R0UWQveUF6UHNRNTJ2YzczcHhiNgp4WjZhYjNCanBjYnNOeCtMNHhsMlIrMzdlcjUyelFobjIxNzE1cUt3QmViRVdPbDV1NGpqangxVzJSMFdHUDcwCldSZzY4eFBZSzREaU5vR3dHRk0rZVFLQmdRQ2FjckNYbko2WitLUlo5V0hZeVlXSmc1dXppcG9ybDB2M3N1a0MKQlAxVytHUTdRWnV4T1hTK2FROUdZR3RwbXdIa3VJUGZkOGVpVlo4VE5ZRHozaG01L2RJSVhkOUZnckxVYUlkVQpaWFljVEhFT1VBejNzZ1QzempadndJRWFsOHBZUVVaM1ZoQmk1c3Rwb2F6eHViWWduampmdFBJeFVLWG80WDJ4CkJ4RnVmd0tCZ1FDWEFKSGNLU2l0dzZQc2FodGZlRys5eGdDN2pDaVh6akpVN0xkSFNCRTl6NWovNjRpMzl0bjgKQ0kvSTNzY3FhaHAxZzVvVnlQVVBESmpTdGIxU3Zvazhqdk9rYWw5cWEycm00NFllWkJBVmIrTm5BanI3WmIvTQpqYXNITjVNSys1VGkrdVc3YW1Vb1NESDBaUlNSSUJ0M1VTU1cydXlRUTdHcjZMRUxYOExPbGc9PQotLS0tLUVORCBSU0EgUFJJVkFURSBLRVktLS0tLQ==",
            "public_key_encrypt_base64_str": b"LS0tLS1CRUdJTiBQVUJMSUMgS0VZLS0tLS0KTUlJQklqQU5CZ2txaGtpRzl3MEJBUUVGQUFPQ0FROEFNSUlCQ2dLQ0FRRUFwc1Uyeno4Q2g2WlBLUlppazRQbApUOTgwUUxuc2lEUjgyaTIrUXNXVnFxcG9UU3dOc0syZ0NXaHFSTExQWXE4VWpkWXpmajcwdVAxUXJBeTBObHovCnBYMTJPNGRJT2VkeG12NU1tS0YrMGxGd1g1cEs0aE1ueFV4bkFxRVFNWHRaOUNTcnNaZEJ6RjhWMEFwWDhTOTMKbjJpNnJGZ254bWRQOHpLSUJtZ0orYzRPaitITXAzK01EeFFrYy9OQTBaaW5OYmJ6QUxDOFlPRDlKNlRCbjl1ZwpIMncwTlN4RTFLU2hsVDhEdlpyUktia3U3MUxUVGR2NVBhaEwvUUcyUkhXK2gxNGxjMXZkSHhkWDdVcEx4a2N4CmluQytCRkdDQXBsR1RFV1h3c0ZzY3dDOExYK2c4bHJvMHd3RDVpaHVLSVJDTnRwRmV1UVdxYmpMeC8vSGI3dEEKY3dJREFRQUIKLS0tLS1FTkQgUFVCTElDIEtFWS0tLS0t",
        }

        # Генерация тестовых ключей

        await insert_test_data(db, "donntu_test@mail.ru", "modex.modex@mail.ru", keys_base64_str_one)
        await insert_test_data(db, "modex.modex@mail.ru", "donntu_test@mail.ru", keys_base64_str_two)

        # Завершение работы с базой данных
        await db.disconnect()

    asyncio.run(main())



