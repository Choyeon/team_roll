from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, ForeignKey, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
from databases import Database
import os
from dotenv import load_dotenv
from datetime import datetime

# 加载环境变量
load_dotenv()

# 获取数据库URL
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./team_roll.db")

# 创建数据库实例（用于异步操作）
database = Database(DATABASE_URL.replace("+aiosqlite", ""))

# 创建SQLAlchemy引擎
# 对于同步连接，移除+aiosqlite后缀
engine_url = DATABASE_URL.replace("+aiosqlite", "")  # 应该是 sqlite:///./team_roll.db
engine = create_engine(
    engine_url,
    connect_args={"check_same_thread": False}  # SQLite需要这个参数
)

# 创建会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 创建基类
Base = declarative_base()


# 依赖项：获取数据库会话
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# 活动模型
class Activity(Base):
    __tablename__ = "activities"
    
    id = Column(String, primary_key=True, index=True)
    name = Column(String, index=True)
    description = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    
    # 活动规则
    roll_min = Column(Integer, default=1)  # Roll点最小值
    roll_max = Column(Integer, default=100)  # Roll点最大值
    max_participations = Column(Integer, default=1)  # 每人最多参与次数
    
    # 关系：一个活动有多个roll结果
    roll_results = relationship("RollResult", back_populates="activity", cascade="all, delete-orphan")


# Roll结果模型
class RollResult(Base):
    __tablename__ = "roll_results"
    
    id = Column(String, primary_key=True, index=True)
    activity_id = Column(String, ForeignKey("activities.id"), index=True)
    name = Column(String, index=True)
    number = Column(Integer)
    ip = Column(String)
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    # 关系：属于一个活动
    activity = relationship("Activity", back_populates="roll_results")


# 管理员会话模型
class AdminSession(Base):
    __tablename__ = "admin_sessions"
    
    id = Column(String, primary_key=True, index=True)
    username = Column(String)
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime)


# 创建所有表
Base.metadata.create_all(bind=engine)
