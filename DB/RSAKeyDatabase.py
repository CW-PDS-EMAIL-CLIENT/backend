from datetime import datetime
from databases import Database
from fastapi import HTTPException

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
        """Создаёт таблицы, если они ещё не существуют."""
        # Таблица для хранения email-адресов
        await self.database.execute("""
        CREATE TABLE IF NOT EXISTS Emails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL
        )
        """)

        # Таблица для хранения личных RSA-ключей
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
            FOREIGN KEY (sender_email_id) REFERENCES Emails (id) 
                ON DELETE CASCADE 
                ON UPDATE CASCADE,
            FOREIGN KEY (current_recipient_email_id) REFERENCES Emails (id) 
                ON DELETE CASCADE 
                ON UPDATE CASCADE
        )
        """)

        # Таблица для хранения публичных RSA-ключей
        await self.database.execute("""
        CREATE TABLE IF NOT EXISTS PublicRSAKeys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            current_sender_email_id INTEGER NOT NULL,
            recipient_email_id INTEGER NOT NULL,
            public_key_sign BLOB NOT NULL,
            public_key_encrypt BLOB NOT NULL,
            create_date DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
            FOREIGN KEY (current_sender_email_id) REFERENCES Emails (id) 
                ON DELETE CASCADE 
                ON UPDATE CASCADE,
            FOREIGN KEY (recipient_email_id) REFERENCES Emails (id) 
                ON DELETE CASCADE 
                ON UPDATE CASCADE
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

        raise HTTPException(status_code=404, detail="Ключи не найдены.")

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

        raise HTTPException(status_code=404, detail="Ключи не найдены.")

    async def get_emails(self):
        """Возвращает список всех email из таблицы Emails."""
        query = "SELECT email FROM Emails"
        rows = await self.database.fetch_all(query)
        return [row["email"] for row in rows] if rows else []

    def get_current_date(self):
        """Возвращает текущую дату и время."""
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

import asyncio
import base64

if __name__ == "__main__":
    import base64

    async def main():
        # Инициализация базы данных
        db = RSAKeyDatabase("sqlite:///rsa_keys.db")
        await db.connect()
        await db.create_tables()

        # Пример данных для тестирования
        first_email = "donntu_test@mail.ru"
        second_email = "modex.modex@mail.ru"

        # Приватные и публичные ключи в формате base64
        private_key_sign_base64 = "<PRIVATE_KEY_SIGN_BASE64>"
        public_key_sign_base64 = "<PUBLIC_KEY_SIGN_BASE64>"
        private_key_encrypt_base64 = "<PRIVATE_KEY_ENCRYPT_BASE64>"
        public_key_encrypt_base64 = "<PUBLIC_KEY_ENCRYPT_BASE64>"

        # Декодирование ключей из base64
        private_key_sign = base64.b64decode(private_key_sign_base64)
        public_key_sign = base64.b64decode(public_key_sign_base64)
        private_key_encrypt = base64.b64decode(private_key_encrypt_base64)
        public_key_encrypt = base64.b64decode(public_key_encrypt_base64)

        # Вставка персональных ключей
        await db.insert_personal_keys(first_email, private_key_sign, public_key_sign, private_key_encrypt, public_key_encrypt)
        await db.insert_personal_keys(second_email, private_key_sign, public_key_sign, private_key_encrypt, public_key_encrypt)

        # Вставка публичных ключей
        await db.insert_public_keys(first_email, second_email, public_key_sign, public_key_encrypt)
        await db.insert_public_keys(second_email, first_email, public_key_sign, public_key_encrypt)

        # Получение публичных ключей
        public_keys_1_to_2 = await db.get_public_keys(first_email, second_email)
        print(f"Публичные ключи для {first_email} к {second_email}:")
        for key in public_keys_1_to_2:
            print(f"Подпись: {key['public_key_sign']}, Шифрование: {key['public_key_encrypt']}")

        public_keys_2_to_1 = await db.get_public_keys(second_email, first_email)
        print(f"Публичные ключи для {second_email} к {first_email}:")
        for key in public_keys_2_to_1:
            print(f"Подпись: {key['public_key_sign']}, Шифрование: {key['public_key_encrypt']}")

        # Получение списка всех e-mail
        emails = await db.get_emails()
        print("Список e-mail:")
        for email in emails:
            print(email)

        # Завершение работы с базой данных
        await db.disconnect()

    import asyncio
    asyncio.run(main())

