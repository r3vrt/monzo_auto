"""Database configuration and models for the Monzo automation app."""

import os
from datetime import datetime
from typing import Optional

from flask import current_app
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    create_engine,
    event,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker, scoped_session
from sqlalchemy.pool import StaticPool

Base = declarative_base()


class TaskExecution(Base):
    """Model for storing task execution history."""
    
    __tablename__ = "task_executions"
    
    id = Column(Integer, primary_key=True)
    task_name = Column(String(50), nullable=False, index=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    success = Column(Boolean, nullable=False)
    result_data = Column(Text, nullable=True)  # JSON string
    error_message = Column(Text, nullable=True)
    execution_time_ms = Column(Integer, nullable=True)
    process_id = Column(Integer, nullable=True)
    
    def __repr__(self):
        return f"<TaskExecution(task_name='{self.task_name}', timestamp='{self.timestamp}', success={self.success})>"


class UserSettings(Base):
    """Model for storing user configuration settings."""
    
    __tablename__ = "user_settings"
    
    id = Column(Integer, primary_key=True)
    key = Column(String(100), unique=True, nullable=False, index=True)
    value = Column(Text, nullable=True)
    data_type = Column(String(20), nullable=False, default="string")  # string, int, float, bool, json
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    def __repr__(self):
        return f"<UserSettings(key='{self.key}', value='{self.value}')>"


class Account(Base):
    """Model for storing account information."""
    
    __tablename__ = "accounts"
    
    id = Column(String(50), primary_key=True)  # Monzo account ID
    name = Column(String(100), nullable=True)
    type = Column(String(50), nullable=True)
    currency = Column(String(10), nullable=True)
    is_selected = Column(Boolean, default=False, nullable=False)
    custom_name = Column(String(100), nullable=True)
    last_sync = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    def __repr__(self):
        return f"<Account(id='{self.id}', name='{self.name}', type='{self.type}')>"


class Pot(Base):
    """Model for storing pot information."""
    
    __tablename__ = "pots"
    
    id = Column(String(50), primary_key=True)  # Monzo pot ID
    account_id = Column(String(50), ForeignKey("accounts.id"), nullable=False)
    name = Column(String(100), nullable=False)
    balance = Column(Integer, nullable=False, default=0)  # In pence
    goal_amount = Column(Integer, nullable=True)  # In pence
    currency = Column(String(10), nullable=True)
    last_sync = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    
    account = relationship("Account", backref="pots")
    
    def __repr__(self):
        return f"<Pot(id='{self.id}', name='{self.name}', balance={self.balance})>"


class Transaction(Base):
    """Model for storing transaction cache."""
    
    __tablename__ = "transactions"
    
    id = Column(String(50), primary_key=True)  # Monzo transaction ID
    account_id = Column(String(50), ForeignKey("accounts.id"), nullable=False)
    amount = Column(Integer, nullable=False)  # In pence
    currency = Column(String(10), nullable=True)
    description = Column(Text, nullable=True)
    category = Column(String(50), nullable=True)
    created = Column(DateTime, nullable=False)
    settled = Column(DateTime, nullable=True)
    notes = Column(Text, nullable=True)
    metadata_json = Column(Text, nullable=True)  # JSON string
    last_sync = Column(DateTime, default=datetime.utcnow, nullable=False)
    
    account = relationship("Account", backref="transactions")
    
    def __repr__(self):
        return f"<Transaction(id='{self.id}', amount={self.amount}, description='{self.description}')>"


class AuditLog(Base):
    """Model for storing audit logs."""
    
    __tablename__ = "audit_logs"
    
    id = Column(Integer, primary_key=True)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    action = Column(String(100), nullable=False)
    resource_type = Column(String(50), nullable=True)
    resource_id = Column(String(100), nullable=True)
    user_agent = Column(String(200), nullable=True)
    ip_address = Column(String(45), nullable=True)
    details_json = Column(Text, nullable=True)  # JSON string
    
    def __repr__(self):
        return f"<AuditLog(action='{self.action}', timestamp='{self.timestamp}')>"


def get_database_url() -> str:
    """Get the database URL from configuration."""
    # For development, use SQLite
    # Use relative path from the app directory
    app_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(app_dir, "..", "data", "monzo_app.db")
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    return f"sqlite:///{db_path}"


def init_database(app):
    """Initialize the database with the Flask app."""
    database_url = get_database_url()
    
    # Create engine
    engine = create_engine(
        database_url,
        connect_args={"check_same_thread": False} if "sqlite" in database_url else {},
        poolclass=StaticPool if "sqlite" in database_url else None,
        echo=app.config.get("SQLALCHEMY_ECHO", False)
    )
    
    # Create session factory
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Session = scoped_session(session_factory)
    
    # Store in app config
    app.config["DATABASE_ENGINE"] = engine
    app.config["DATABASE_SESSION"] = Session
    
    # Create tables
    Base.metadata.create_all(bind=engine)
    
    return engine, Session


def get_db_session():
    """Get the current database session."""
    return current_app.config.get("DATABASE_SESSION")()


def close_db_session(session):
    """Close the database session."""
    if session:
        session.close()


@event.listens_for(Base.metadata, "before_create")
def receive_before_create(target, connection, **kw):
    """Handle database creation events."""
    pass 