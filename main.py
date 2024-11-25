from fastapi import FastAPI, HTTPException, Depends
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey, BLOB
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, Session
from datetime import datetime

# Инициализация базы данных
DATABASE_URL = "sqlite:///./rsa_keys.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Определение моделей
class Email(Base):
    __tablename__ = "emails"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, nullable=False)

    personal_keys = relationship("PersonalRSAKey", back_populates="email_ref")
    public_keys = relationship("PublicRSAKey", back_populates="email_ref")


class PersonalRSAKey(Base):
    __tablename__ = "personal_rsa_keys"
    id = Column(Integer, primary_key=True, index=True)
    email_id = Column(Integer, ForeignKey("emails.id", ondelete="CASCADE"), nullable=False)
    private_key_sign = Column(BLOB, nullable=False)
    public_key_sign = Column(BLOB, nullable=False)
    private_key_encrypt = Column(BLOB, nullable=False)
    public_key_encrypt = Column(BLOB, nullable=False)
    create_date = Column(DateTime, default=datetime.utcnow, nullable=False)

    email_ref = relationship("Email", back_populates="personal_keys")


class PublicRSAKey(Base):
    __tablename__ = "public_rsa_keys"
    id = Column(Integer, primary_key=True, index=True)
    email_id = Column(Integer, ForeignKey("emails.id", ondelete="CASCADE"), nullable=False)
    public_key_sign = Column(BLOB, nullable=False)
    public_key_encrypt = Column(BLOB, nullable=False)
    create_date = Column(DateTime, default=datetime.utcnow, nullable=False)

    email_ref = relationship("Email", back_populates="public_keys")


# Создание таблиц
Base.metadata.create_all(bind=engine)

# Инициализация приложения FastAPI
app = FastAPI()


# Dependency для получения сессии
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# CRUD и эндпоинты
@app.post("/emails/")
def create_email(email: str, db: Session = Depends(get_db)):
    existing_email = db.query(Email).filter(Email.email == email).first()
    if existing_email:
        return {"message": "Email already exists.", "email_id": existing_email.id}

    new_email = Email(email=email)
    db.add(new_email)
    db.commit()
    db.refresh(new_email)
    return {"email_id": new_email.id, "message": "Email created successfully."}


@app.post("/personal-keys/")
def create_personal_key(email: str, private_key_sign: bytes, public_key_sign: bytes,
                        private_key_encrypt: bytes, public_key_encrypt: bytes, db: Session = Depends(get_db)):
    email_entry = db.query(Email).filter(Email.email == email).first()
    if not email_entry:
        email_entry = Email(email=email)
        db.add(email_entry)
        db.commit()
        db.refresh(email_entry)

    new_key = PersonalRSAKey(
        email_id=email_entry.id,
        private_key_sign=private_key_sign,
        public_key_sign=public_key_sign,
        private_key_encrypt=private_key_encrypt,
        public_key_encrypt=public_key_encrypt,
    )
    db.add(new_key)
    db.commit()
    db.refresh(new_key)
    return {"message": "Personal keys created successfully.", "key_id": new_key.id}


@app.post("/public-keys/")
def create_public_key(email: str, public_key_sign: bytes, public_key_encrypt: bytes, db: Session = Depends(get_db)):
    email_entry = db.query(Email).filter(Email.email == email).first()
    if not email_entry:
        email_entry = Email(email=email)
        db.add(email_entry)
        db.commit()
        db.refresh(email_entry)

    new_key = PublicRSAKey(
        email_id=email_entry.id,
        public_key_sign=public_key_sign,
        public_key_encrypt=public_key_encrypt,
    )
    db.add(new_key)
    db.commit()
    db.refresh(new_key)
    return {"message": "Public keys created successfully.", "key_id": new_key.id}


@app.get("/personal-keys/{email}")
def get_personal_keys(email: str, db: Session = Depends(get_db)):
    email_entry = db.query(Email).filter(Email.email == email).first()
    if not email_entry:
        raise HTTPException(status_code=404, detail="Email not found")

    keys = db.query(PersonalRSAKey).filter(PersonalRSAKey.email_id == email_entry.id).all()
    return [{"private_key_sign": k.private_key_sign, "public_key_sign": k.public_key_sign,
             "private_key_encrypt": k.private_key_encrypt, "public_key_encrypt": k.public_key_encrypt}
            for k in keys]


@app.get("/public-keys/{email}")
def get_public_keys(email: str, db: Session = Depends(get_db)):
    email_entry = db.query(Email).filter(Email.email == email).first()
    if not email_entry:
        raise HTTPException(status_code=404, detail="Email not found")

    keys = db.query(PublicRSAKey).filter(PublicRSAKey.email_id == email_entry.id).all()
    return [{"public_key_sign": k.public_key_sign, "public_key_encrypt": k.public_key_encrypt} for k in keys]
