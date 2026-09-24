from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from app.config import DATABASE_URL
from app.db.models import Base

# SQLite connect_args for multithreading in FastAPI / Telegram bot
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(DATABASE_URL, echo=False, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db():
    """Create all tables if they do not exist, and add new columns safely."""
    Base.metadata.create_all(bind=engine)
    if DATABASE_URL.startswith("sqlite"):
        from sqlalchemy import text
        with engine.connect() as conn:
            for col, col_type in [
                ("tagline", "VARCHAR(500)"),
                ("about_us", "VARCHAR(2000)"),
                ("trust_badges", "VARCHAR(1000)"),
                ("whatsapp", "VARCHAR(50)"),
                ("cta_text", "VARCHAR(100)"),
                ("logo_url", "VARCHAR(500)"),
                ("hero_image_url", "VARCHAR(500)"),
            ]:
                try:
                    conn.execute(text(f"ALTER TABLE businesses ADD COLUMN {col} {col_type};"))
                    conn.commit()
                except Exception:
                    pass


def get_db():
    """Dependency or context manager for acquiring a database session."""
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
