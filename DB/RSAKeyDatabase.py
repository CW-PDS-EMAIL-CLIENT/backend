from datetime import datetime

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


import asyncio
import base64

if __name__ == "__main__":
    async def main():
        db = RSAKeyDatabase("sqlite:/..//rsa_keys.db")
        await db.connect()
        await db.create_tables()

        # Пример использования
        email = "donntu_test@mail.ru" # modex.modex@mail.ru
        private_key_sign_base64 = "LS0tLS1CRUdJTiBSU0EgUFJJVkFURSBLRVktLS0tLQpNSUlFb3dJQkFBS0NBUUVBcUpHYXE4d2dBbDB3VjhPRVZRWFc2VWNHQlMwU1ZGcUhkVk1iVXA1elhSV0VXOUVJCmhGeWkwREdSeTRrdjZaYllBbGhCUTJsbWJKVHkvZ1czMEZIWEdGU3h3M2NLNlBxTUhueEtSUENxMzVqV3Zad0EKNmNkQkxoMTU3Y0JoOGwvZzdkdjJUVGhoMFpTVUlhZjNmZnFtTlBhOEV3TE96UXNSOXVEN2dMaHJTaTFVQWprSwoyNlJjSjliSFZqbnY2eGkzOTVCZkYybDAyUlV6MWVyUUdGSTQ4eHRUZlRIdlBCcitwVjRJTTJxU3RxbFRsR3EvClZLRFIvenlSL1AwckE3OUpPYmxHVzRyeUpCQzNRYm1hVis1aTFRSlBQVjV0YWNoM0FmMEhwbkREUWV6VHVFNFMKWEVKQlFhbnZTS3hvQTI2ZHk1clVteUxITkFPWWN1L2pyZUlFSHdJREFRQUJBb0lCQUVJK1dneWFYcGZmUEVDNQpGbmQ5SUh3ekM0UWNOc0JNaFVBUGhVUzkvUEwvSWpFYzM5NTRNd2xpK1hzRmNmMDNhTExmTU9LSGVKZENINDNBCi9IL1NzWmNmclczMWlhV04xR09rajJFeFBNMDYyR1RSK2kva3ZGSWRoazF1MVc3MHk4VmR0QmliaUNGZTVLbW4KUXVUUWkrRnpkdXgzcFlKQmovRTNiODZoYXBST3dOUlpmN1Y5Ti94OXRyeXNudnFpQ2t1MjdUdmEyYWNka0gyLwpOWUFDUlRJc3pMeHRtb1R2SHB0MnhkSXJOOFlJR2twcUpCSzlkaGhqdXBEd2tyV0ZZV1FLajBkWW5SejgxWkN2CnpyMGM5SFFlWmZUYjZHVklMdjJyb3VzMS8za3RWRHJkVEdvUnozQW1wYmozYUhZWkl4b21DT0xnNXozakxkZVoKa0dya0Eya0NnWUVBdkprM1RlNmg2dkxpNUQ4Lzc5TDlBM0lTUmlHM2piNm9mNFF1QlV0b0VZQXNNZFZFWlNMWAoyaCtMZkQ5d29VNUIzNUlwcitTVnNRNmMwalpyVFZrNlNLdUwrQUdEZFRINWtQNEhWdStzNnpYWTdjVVVHTi9CCkZjeTJBR2JCbVZ4ei84VXFiS1E1NGFHRzRtQzVTUTdJdFZVZ3lSQTcvZldNSllUcU1ySy96N2NDZ1lFQTVNL2cKcnBGTndNRXh2ZElmbnkweUhabUl6YXZhejQrR2xrd2YxUDNrTVdvVDNadi9HcDI1K0ZrM3hKakZlYWgxY2d1awpwajVralBib2FUbnY2Q2Jnekk0VC9GVW1WNTZ6QU5yaFZIcmhvbzFKTjhUY0R1WEhnS1BQSVlxbkVoYWJmK1pyCnRHV0lpanFTOGtWS1FYb3RIWFNESVVIazY5RkVOTFprMWtHb250a0NnWUJWa285dFpPRkM0WUhoWG5GOE41ZGwKZ05TWnphS2pSZWJlTlBOTW83Sk1mb09PK04xWHBqK2FVTVhSVWxlZ1dRbTZqMjhxeCtURHVZV2VPK0xqN2FCcwphS25SbFo0NEJyemQ5T1VQcFNBb2VQNDhwRGRDTWdSQ0IraHN0ak1SaXNsM085Yk1CSmZlc0pPckU0ZitoaDY3CmFDekFEZ1dxYlVkeG5xVkU2NlhzY1FLQmdFOHVIS3RzUHdMZ0dDMS9CRkJhSElpZnMvYXdiT1Q4M3U4dDRxb2IKUGhkWGhRNWdTRlJXbHA5NWlGSHhLQTBrblpmY3JacVY1c2ZkUGFvRVVaLzlyRGM5UjI4L3JDZ1FGQlBNcXNOSQpUc0tvcjlpcnVCY3pydWsyUnB4dDFjanRwOXdIeWVmQVp4S21tR2xjVHdqL2xaTW0yYVh0bnFGNFptanpZVXUvCnB2RnBBb0dCQUxMWWM5blhIRXdDYTNid1RMKzJld2orNmlzbG1iYWd0cURUL0VrY1NwSk8yRTEyeXdmSUQ2R1UKdm1MZnk0YjAvZzNJMUVtSVVyLzVoNmVOT3VSUVlMZjVZaFV0U0dGOHdHTW5kNCtlK1cwRFMvbXQ5cDZEbkwzUApMU3g5RVB0MnkxWTB0SnRvRDZ4NFlGVVgzM1I4WlVlaEh0VEcxMTBMdGpxME01NDd4Q2xtCi0tLS0tRU5EIFJTQSBQUklWQVRFIEtFWS0tLS0t"
        public_key_sign_base64 = "LS0tLS1CRUdJTiBQVUJMSUMgS0VZLS0tLS0KTUlJQklqQU5CZ2txaGtpRzl3MEJBUUVGQUFPQ0FROEFNSUlCQ2dLQ0FRRUFxSkdhcTh3Z0FsMHdWOE9FVlFYVwo2VWNHQlMwU1ZGcUhkVk1iVXA1elhSV0VXOUVJaEZ5aTBER1J5NGt2NlpiWUFsaEJRMmxtYkpUeS9nVzMwRkhYCkdGU3h3M2NLNlBxTUhueEtSUENxMzVqV3Zad0E2Y2RCTGgxNTdjQmg4bC9nN2R2MlRUaGgwWlNVSWFmM2ZmcW0KTlBhOEV3TE96UXNSOXVEN2dMaHJTaTFVQWprSzI2UmNKOWJIVmpudjZ4aTM5NUJmRjJsMDJSVXoxZXJRR0ZJNAo4eHRUZlRIdlBCcitwVjRJTTJxU3RxbFRsR3EvVktEUi96eVIvUDByQTc5Sk9ibEdXNHJ5SkJDM1FibWFWKzVpCjFRSlBQVjV0YWNoM0FmMEhwbkREUWV6VHVFNFNYRUpCUWFudlNLeG9BMjZkeTVyVW15TEhOQU9ZY3UvanJlSUUKSHdJREFRQUIKLS0tLS1FTkQgUFVCTElDIEtFWS0tLS0t"
        private_key_encrypt_base64 = "LS0tLS1CRUdJTiBSU0EgUFJJVkFURSBLRVktLS0tLQpNSUlFb3dJQkFBS0NBUUVBbENaK3dJY3I1ZW44K2UxSU80NzhMQVVsVEc1VmdwNFIvQ2ltWUtCUkl6K1RsTXhOCjNPYU9xNFIxQUJRTWNwNEdEbUVLMXFzdGh4WllPVFIrdC9GU0s5VHYyQVVTSDliL1c5Ui95WmR0QTlrdisvVFMKM3hEd3daMDBMOXJzajQ0Sm52R1l6WlpVeDBod29WSXZXVVFwWU01ZTE5UFo3QnpsOTF3MC9RaGtHVkZaVVhXZApSUmFBQ3hjQTEwWG1uYTR0NHVuYzlvMzdFWE81OFBjb1h1M1pYSGZWRnRTRTZvQzFaNFlLZkxXYnBnRWYza0pBCjk2dVMxQk1OMkdrV1FWUytlR1ROdEl5aHdHei9KY0M4VndYcURLUjRMSDRDY28vSk93WlVFV1d1bDhhSGJZdm0Kb0ZIb0ZMM0JtcUNEZzYxa0JQOTBLcFpNdjRxanBVdFRoSjhWZHdJREFRQUJBb0lCQUR6SXdvNnBweGd3OWN0eApVSWFuTnMyMDJzWE9LeVZwUjRYSEErUjNRbk1NM2JkYVQ4UUhrSmZNdzloaFlXNFJhZml5VmlrWG1KbHBVSTgvCis1SHE0RVQ5bTk1c3ppL2tIV2VHKzFzeDF0ZVNYNzZuaDNGZ1dQZUhVV2NsRXBRZnVkRE4zVnpVaGpveGZZeWkKMUt4eWErdTlJR3E3RUJseERlVjhubjBHMlZNTlRxS0NlSk84Y0JyNm9VZmxMYzB0K2Jnamhad2JGVE54NVlGSApMc1hhR1lVNFBWTlhKNFp2cFdOZ3oxdGV3K3BZdUhEWVFMQW5hUTRPUWhmdmFWMVN0bkxaK0dOWTdna2Z6NzZqCkJPZmV1azBMd2UrRndHeFZ4bUlUSjdLaC9lZUYydThYNFh2TVVqOEFSYXV5SmhHbVZ5T0t2N1lBTW9EamhQSkcKalloR2VPa0NnWUVBd2toZUd3aS8vUEpwaVoxcXhKYzVYY2pnamlwYzBidUxjQ2cvNkM2MmxJWWFzUGpMT05CZQpDUHFYWUNoS0RhSVU3b3ZwdFEwRHBrYXA2UXB0VU5jY2pSQXFGV2d1QWxZRHg3SDdTWHJqRVE4dVh4LzFHNDdxCis0Tk1mRXRQR2htSnpPMStuNTFLWlNKNlZkbUZZTmM1Y3kyT2t3c1gxeERSdTA4dnlFVG1oUXNDZ1lFQXd6YUQKZ29Uem1wYmR6eGlwcURsNFRHUndEb2NIRTlCZXhkaDV0WDNaSjJ6VWZJVXlmQmwxTmFDQTdIVlNmbWFER3liNwpmS2EwMG82QXF2VTJrVklURUpNZHBFT1BYVm4vdUVmd3luZy96c2JQK1FKb1ppYUxGT0JSRnZIejRiMFE2M2NhCnI3dHlGYjNpcjF4TnFlTXUzSFdEVEtSTVNtMzBDcTNmbXB0NG5NVUNnWUJSalhzak1mc1ZQTlNjVlozWncvanEKcTBYSHAzU3EvV1M4d2NpQnVBb2dNbUxGNHNtN29ZdTNqU2s1emUrMzVVK1FDdDhoaHNML2F5NHJpcHIwa2plRAo1ME1qRlVZcTZOeFJXUjY0YTRNaFNCUVpEaHNmWkZDekh4eGVHR2F0K0FabUpWTS93UkRYZnkrSEZmWHMvcXM0CjgraWpSTWJQR2xwUG5CL2NteitBblFLQmdRRENWbFBIck1uQy9Td21EbnhmajQ3MkpncjBPM0pOUkdRRS9BUDIKTFNud3VNUTBqbmw2MS9FNmlPV3dBUUExKzZITGR4eG50S0pROXpLYWZ2RnE3RlUwYS9EWFpiYWtqWU1wRnQxZApBeWNxbC92VS9wT21GZnJodG9xam1BMWRqbFg0dzZLYWpiWCtkUUhsNTdNZFRLQ0xNcVdhdC9tSEl6MFBJSmQ1CkdBdVRyUUtCZ0dBTFlWbEo4TDJqcE91M29VREJLaXl0NlVTaEdTNm15VHVSaGtKa2RjaklvYVM4NUxxZTh2QncKcit5NzUxU3pzcS9QUGU5K1JWSEdhR284MjdCTkpNenRRTGVjRU5BTmlZU2xQbEhQMkRzOWtMWi9iOS9IVE53RAo5ZnRNUFlKSDl6bkpySWNuZ3RFK0swbG80SkJBZnFQdXByUzFJVnk5MUkvQ0FNTk0yWHFyCi0tLS0tRU5EIFJTQSBQUklWQVRFIEtFWS0tLS0t"
        public_key_encrypt_base64 = "LS0tLS1CRUdJTiBQVUJMSUMgS0VZLS0tLS0KTUlJQklqQU5CZ2txaGtpRzl3MEJBUUVGQUFPQ0FROEFNSUlCQ2dLQ0FRRUFsQ1ord0ljcjVlbjgrZTFJTzQ3OApMQVVsVEc1VmdwNFIvQ2ltWUtCUkl6K1RsTXhOM09hT3E0UjFBQlFNY3A0R0RtRUsxcXN0aHhaWU9UUit0L0ZTCks5VHYyQVVTSDliL1c5Ui95WmR0QTlrdisvVFMzeER3d1owMEw5cnNqNDRKbnZHWXpaWlV4MGh3b1ZJdldVUXAKWU01ZTE5UFo3QnpsOTF3MC9RaGtHVkZaVVhXZFJSYUFDeGNBMTBYbW5hNHQ0dW5jOW8zN0VYTzU4UGNvWHUzWgpYSGZWRnRTRTZvQzFaNFlLZkxXYnBnRWYza0pBOTZ1UzFCTU4yR2tXUVZTK2VHVE50SXlod0d6L0pjQzhWd1hxCkRLUjRMSDRDY28vSk93WlVFV1d1bDhhSGJZdm1vRkhvRkwzQm1xQ0RnNjFrQlA5MEtwWk12NHFqcFV0VGhKOFYKZHdJREFRQUIKLS0tLS1FTkQgUFVCTElDIEtFWS0tLS0t"

        private_key_sign = base64.b64decode(private_key_sign_base64.encode("utf-8"))
        public_key_sign = base64.b64decode(public_key_sign_base64.encode("utf-8"))
        private_key_encrypt = base64.b64decode(private_key_encrypt_base64.encode("utf-8"))
        public_key_encrypt = base64.b64decode(public_key_encrypt_base64.encode("utf-8"))

        await db.insert_personal_keys(email, private_key_sign, public_key_sign, private_key_encrypt, public_key_encrypt)
        await db.insert_public_keys(email, public_key_sign, public_key_encrypt)

        # Получение данных
        public_keys = await db.get_public_keys(email)
        print(f"Публичные ключи для {email}:")
        for key in public_keys:
            print(f"Подпись: {key['public_key_sign']}, Шифрование: {key['public_key_encrypt']}")

        emails = await db.get_emails()
        print(emails)

        await db.disconnect()

    asyncio.run(main())
