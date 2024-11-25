import base64
from datetime import datetime

import uvicorn
from databases import Database
from fastapi import FastAPI, Depends, HTTPException

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
        await self.database.execute("""
        CREATE TABLE IF NOT EXISTS Emails (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL
        )
        """)
        await self.database.execute("""
        CREATE TABLE IF NOT EXISTS PersonalRSAKeys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email_id INTEGER NOT NULL,
            private_key_sign BLOB NOT NULL,
            public_key_sign BLOB NOT NULL,
            private_key_encrypt BLOB NOT NULL,
            public_key_encrypt BLOB NOT NULL,
            create_date DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
            FOREIGN KEY (email_id) REFERENCES Emails (id) ON DELETE CASCADE ON UPDATE CASCADE
        )
        """)
        await self.database.execute("""
        CREATE TABLE IF NOT EXISTS PublicRSAKeys (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email_id INTEGER NOT NULL,
            public_key_sign BLOB NOT NULL,
            public_key_encrypt BLOB NOT NULL,
            create_date DATETIME DEFAULT CURRENT_TIMESTAMP NOT NULL,
            FOREIGN KEY (email_id) REFERENCES Emails (id) ON DELETE CASCADE ON UPDATE CASCADE
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
        else:
            raise HTTPException(status_code=500, detail="Не удалось вставить email.")

    async def insert_personal_keys(
        self,
        email: str,
        private_key_sign: bytes,
        public_key_sign: bytes,
        private_key_encrypt: bytes,
        public_key_encrypt: bytes,
        create_date: str = None
    ):
        """Вставляет личные RSA-ключи для указанного email."""
        email_id = await self.insert_email(email)
        if not create_date:
            create_date = self.get_current_date()

        query = """
        INSERT INTO PersonalRSAKeys (
            email_id, private_key_sign, public_key_sign, private_key_encrypt, public_key_encrypt, create_date
        ) VALUES (:email_id, :private_key_sign, :public_key_sign, :private_key_encrypt, :public_key_encrypt, :create_date)
        """
        await self.database.execute(query, {
            "email_id": email_id,
            "private_key_sign": private_key_sign,
            "public_key_sign": public_key_sign,
            "private_key_encrypt": private_key_encrypt,
            "public_key_encrypt": public_key_encrypt,
            "create_date": create_date,
        })

    async def insert_public_keys(
        self, email: str, public_key_sign: bytes, public_key_encrypt: bytes, create_date: str = None
    ):
        """Вставляет публичные RSA-ключи для указанного email."""
        email_id = await self.insert_email(email)
        if not create_date:
            create_date = self.get_current_date()

        query = """
        INSERT INTO PublicRSAKeys (email_id, public_key_sign, public_key_encrypt, create_date)
        VALUES (:email_id, :public_key_sign, :public_key_encrypt, :create_date)
        """
        await self.database.execute(query, {
            "email_id": email_id,
            "public_key_sign": public_key_sign,
            "public_key_encrypt": public_key_encrypt,
            "create_date": create_date,
        })

    async def get_public_keys(self, email: str, date_limit: str = None):
        """Получает публичные ключи для указанного email до указанной даты."""
        if not date_limit:
            date_limit = self.get_current_date()

        query = """
        SELECT pk.public_key_sign, pk.public_key_encrypt
        FROM Emails em
        LEFT JOIN PublicRSAKeys pk ON em.id = pk.email_id
        WHERE em.email = :email AND pk.create_date <= :date_limit
        ORDER BY pk.create_date DESC
        """
        rows = await self.database.fetch_all(query, {"email": email, "date_limit": date_limit})
        return [{"public_key_sign": row["public_key_sign"], "public_key_encrypt": row["public_key_encrypt"]} for row in rows]

    async def get_personal_keys(self, email: str, date_limit: str = None):
        """Получает личные ключи для указанного email до указанной даты."""
        if not date_limit:
            date_limit = self.get_current_date()

        query = """
        SELECT prk.private_key_sign, prk.public_key_sign, prk.private_key_encrypt, prk.public_key_encrypt
        FROM Emails em
        LEFT JOIN PersonalRSAKeys prk ON em.id = prk.email_id
        WHERE em.email = :email AND prk.create_date <= :date_limit
        ORDER BY prk.create_date DESC
        LIMIT 1
        """
        row = await self.database.fetch_one(query, {"email": email, "date_limit": date_limit})
        if row:
            return {
                "private_key_sign": row["private_key_sign"],
                "public_key_sign": row["public_key_sign"],
                "private_key_encrypt": row["private_key_encrypt"],
                "public_key_encrypt": row["public_key_encrypt"],
            }
        return None

    async def get_emails(self):
        query = """
        SELECT email 
        FROM Emails
        """
        column = await self.database.fetch_all(query)
        if column:
            return [row["email"] for row in column]  # Исправлено
        return None

    def get_current_date(self):
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


# Инициализация FastAPI
app = FastAPI()
db = RSAKeyDatabase()


@app.on_event("startup")
async def startup():
    await db.connect()
    await db.create_tables()


@app.on_event("shutdown")
async def shutdown():
    await db.disconnect()


# Примеры маршрутов
@app.post("/personal_keys/")
async def create_personal_keys(email: str, private_key_sign: str, public_key_sign: str, private_key_encrypt: str, public_key_encrypt: str):
    await db.insert_personal_keys(
        email=email,
        private_key_sign=base64.b64decode(private_key_sign),
        public_key_sign=base64.b64decode(public_key_sign),
        private_key_encrypt=base64.b64decode(private_key_encrypt),
        public_key_encrypt=base64.b64decode(public_key_encrypt),
    )
    return {"message": "Keys inserted successfully."}


@app.get("/public_keys/")
async def get_public_keys(email: str):
    keys = await db.get_public_keys(email)
    return keys

@app.put("/emails/put/")
async def put_email(email: str):
    email_id = await db.insert_email(email)
    return email_id

@app.put("/emails/get/")
async def get_emails():
    emails = await db.get_emails()
    return emails

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)