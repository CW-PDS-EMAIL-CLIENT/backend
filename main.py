import base64
from datetime import datetime

import uvicorn
from databases import Database
from fastapi import FastAPI, Depends, HTTPException

from DB.RSAKeyDatabase import RSAKeyDatabase

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