from fastapi import FastAPI, Request, Form, HTTPException, Depends, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import Dict, Set, List
from pydantic import BaseModel
import random
from datetime import datetime, timedelta
import uuid
import logging
import os
from dotenv import load_dotenv
from sqlalchemy.orm import Session

# 加载环境变量
load_dotenv()

# 导入数据库配置和模型
from database import get_db, Activity as DB_Activity, RollResult as DB_RollResult, AdminSession as DB_AdminSession

# Pydantic模型定义
class Activity(BaseModel):
    id: str = uuid.uuid4().hex
    name: str
    description: str = ""
    created_at: datetime = datetime.now()
    is_active: bool = True

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 从环境变量获取配置
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "choyeon")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "choyeon")
SESSION_EXPIRE_TIME = timedelta(hours=int(os.getenv("SESSION_EXPIRE_TIME", 2)))
APP_NAME = os.getenv("APP_NAME", "Team Roll")
DEBUG = os.getenv("DEBUG", "True").lower() == "true"

app = FastAPI(title=APP_NAME, docs_url="/docs", redoc_url="/redoc", debug=DEBUG)

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# IP检测直接通过X-Forwarded-For头处理，无需额外中间件

# 挂载静态文件目录
app.mount("/static", StaticFiles(directory="static"), name="static")

# 设置模板目录
templates = Jinja2Templates(directory="templates")

# WebSocket连接管理器，用于管理所有活动的连接
class ConnectionManager:
    def __init__(self):
        # 存储活动ID对应的WebSocket连接集合
        self.active_connections: Dict[str, Set[WebSocket]] = {}
    
    async def connect(self, websocket: WebSocket, activity_id: str):
        await websocket.accept()
        if activity_id not in self.active_connections:
            self.active_connections[activity_id] = set()
        self.active_connections[activity_id].add(websocket)
    
    def disconnect(self, websocket: WebSocket, activity_id: str):
        if activity_id in self.active_connections:
            self.active_connections[activity_id].discard(websocket)
            if not self.active_connections[activity_id]:
                del self.active_connections[activity_id]
    
    async def broadcast(self, message: dict, activity_id: str):
        if activity_id in self.active_connections:
            for connection in self.active_connections[activity_id]:
                await connection.send_json(message)

# 创建WebSocket连接管理器实例
manager = ConnectionManager()


async def get_current_admin(request: Request, db: Session = Depends(get_db)):
    """获取当前登录的管理员，包含会话过期检查"""
    session_id = request.cookies.get("session_id")
    if not session_id:
        raise HTTPException(status_code=307, detail="Not authenticated", headers={"Location": "/admin/login"})
    
    # 从数据库获取会话
    session = db.query(DB_AdminSession).filter(DB_AdminSession.id == session_id).first()
    if not session:
        raise HTTPException(status_code=307, detail="Not authenticated", headers={"Location": "/admin/login"})
    
    # 检查会话是否过期
    if datetime.now() > session.expires_at:
        db.delete(session)
        db.commit()
        raise HTTPException(status_code=307, detail="Session expired", headers={"Location": "/admin/login"})
    
    # 更新会话过期时间
    session.expires_at = datetime.now() + SESSION_EXPIRE_TIME
    db.commit()
    return session_id


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request, db: Session = Depends(get_db)):
    """主页显示所有活动"""
    # 从数据库获取所有活动
    db_activities = db.query(DB_Activity).all()
    
    # 转换为字典格式并处理日期
    activities = []
    for activity in db_activities:
        activity_dict = {
            "id": activity.id,
            "name": activity.name,
            "description": activity.description,
            "created_at": activity.created_at.isoformat(),
            "is_active": activity.is_active,
            "roll_min": activity.roll_min,
            "roll_max": activity.roll_max,
            "max_participations": activity.max_participations
        }
        activities.append(activity_dict)
    
    return templates.TemplateResponse("index.html", {
        "request": request,
        "activities": activities
    })


@app.get("/admin/login", response_class=HTMLResponse)
async def admin_login_page(request: Request):
    """管理员登录页面"""
    return templates.TemplateResponse("admin_login.html", {"request": request})


@app.post("/admin/login")
async def admin_login(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db)
):
    """管理员登录处理"""
    if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
        # 创建会话ID
        session_id = str(uuid.uuid4())
        
        # 创建数据库会话记录
        db_session = DB_AdminSession(
            id=session_id,
            username=username,
            created_at=datetime.now(),
            expires_at=datetime.now() + SESSION_EXPIRE_TIME
        )
        db.add(db_session)
        db.commit()
        
        # 创建响应并设置Cookie，添加安全属性
        response = RedirectResponse(url="/admin", status_code=303)
        response.set_cookie(
            "session_id", 
            session_id, 
            httponly=True,
            secure=False,  # 在生产环境中应设置为True
            samesite="lax"
        )
        logger.info(f"Admin {username} logged in successfully")
        return response
    else:
        # 登录失败，返回登录页面并显示错误
        logger.warning(f"Failed login attempt for username: {username}")
        return templates.TemplateResponse("admin_login.html", {
            "request": request,
            "error": "用户名或密码错误"
        })


@app.get("/admin/logout")
async def admin_logout(request: Request, admin: str = Depends(get_current_admin), db: Session = Depends(get_db)):
    """管理员登出"""
    session_id = request.cookies.get("session_id")
    if session_id:
        # 从数据库中删除会话
        session = db.query(DB_AdminSession).filter(DB_AdminSession.id == session_id).first()
        if session:
            db.delete(session)
            db.commit()
            logger.info(f"Admin logged out successfully")
    
    response = RedirectResponse(url="/admin/login", status_code=303)
    response.delete_cookie("session_id")
    return response


@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request, admin: str = Depends(get_current_admin), db: Session = Depends(get_db)):
    """管理员页面"""
    # 从数据库获取所有活动，按创建时间倒序排列
    db_activities = db.query(DB_Activity).order_by(DB_Activity.created_at.desc()).all()
    
    # 转换为字典格式并处理日期
    activities = []
    for activity in db_activities:
        activity_dict = {
            "id": activity.id,
            "name": activity.name,
            "description": activity.description,
            "created_at": activity.created_at.isoformat(),
            "is_active": activity.is_active,
            "roll_min": activity.roll_min,
            "roll_max": activity.roll_max,
            "max_participations": activity.max_participations
        }
        activities.append(activity_dict)
    
    return templates.TemplateResponse("admin.html", {
        "request": request,
        "activities": activities
    })


@app.post("/admin/create_activity")
async def create_activity(
    request: Request,
    name: str = Form(...),
    description: str = Form(""),
    roll_min: int = Form(default=1),
    roll_max: int = Form(default=100),
    max_participations: int = Form(default=1),
    admin: str = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """创建新活动"""
    # 确保roll_max大于roll_min
    if roll_max < roll_min:
        roll_max = roll_min
    
    # 创建活动ID
    activity_id = uuid.uuid4().hex
    
    # 创建数据库活动记录
    db_activity = DB_Activity(
        id=activity_id,
        name=name,
        description=description,
        created_at=datetime.now(),
        is_active=True,
        roll_min=roll_min,
        roll_max=roll_max,
        max_participations=max_participations
    )
    
    # 保存到数据库
    db.add(db_activity)
    db.commit()
    
    logger.info(f"Created new activity: {name} (ID: {activity_id}) with rules: {roll_min}-{roll_max}, max participations: {max_participations}")
    return RedirectResponse(url="/admin", status_code=303)


@app.post("/admin/delete_activity/{activity_id}")
async def delete_activity(
    request: Request,
    activity_id: str,
    admin: str = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """删除活动"""
    # 从数据库中查找活动
    db_activity = db.query(DB_Activity).filter(DB_Activity.id == activity_id).first()
    
    if db_activity:
        # 删除活动（级联删除相关的roll结果）
        db.delete(db_activity)
        db.commit()
        
        # 发送WebSocket广播，通知所有客户端活动已被删除
        await manager.broadcast({
            "type": "activity_deleted",
            "activity_id": activity_id
        }, activity_id)
        
        logger.info(f"Deleted activity: {db_activity.name} (ID: {activity_id})")
    
    # 重定向到管理员页面
    return RedirectResponse(url="/admin", status_code=303)


@app.post("/admin/end_activity/{activity_id}")
async def end_activity(
    request: Request,
    activity_id: str,
    admin: str = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """结束活动"""
    # 从数据库中查找活动
    db_activity = db.query(DB_Activity).filter(DB_Activity.id == activity_id).first()
    
    if db_activity:
        # 将活动标记为已结束
        db_activity.is_active = False
        db.commit()
        
        # 发送WebSocket广播，通知所有客户端活动已结束
        await manager.broadcast({
            "type": "activity_ended",
            "activity_id": activity_id
        }, activity_id)
        
        logger.info(f"Ended activity: {db_activity.name} (ID: {activity_id})")
    
    # 重定向回管理员页面
    return RedirectResponse(url="/admin", status_code=303)


@app.post("/admin/delete_roll/{activity_id}/{result_index}")
async def delete_roll_result(
    request: Request,
    activity_id: str,
    result_index: int,
    admin: str = Depends(get_current_admin),
    db: Session = Depends(get_db)
):
    """删除单条Roll点结果"""
    # 从数据库中查找活动
    db_activity = db.query(DB_Activity).filter(DB_Activity.id == activity_id).first()
    if not db_activity:
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error_message": "活动不存在或已被删除。",
            "activity_id": activity_id
        })
    
    # 获取该活动的所有roll结果，按时间排序
    db_results = db.query(DB_RollResult).filter(DB_RollResult.activity_id == activity_id).order_by(DB_RollResult.timestamp).all()
    if not db_results:
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error_message": "该活动没有Roll点结果。",
            "activity_id": activity_id
        })
    
    # 检查result_index是否有效
    if result_index < 0 or result_index >= len(db_results):
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error_message": "Roll点结果不存在或已被删除。",
            "activity_id": activity_id
        })
    
    # 获取要删除的结果
    deleted_result = db_results[result_index]
    
    # 从数据库中删除
    db.delete(deleted_result)
    db.commit()
    
    logger.info(f"Deleted roll result for activity {activity_id}: {deleted_result.name} - {deleted_result.number}")
    
    # 发送WebSocket广播，通知所有客户端有Roll点结果被删除
    await manager.broadcast({
        "type": "roll_deleted",
        "result_id": deleted_result.id
    }, activity_id)
    
    # 重定向回活动页面
    return RedirectResponse(url=f"/activity/{activity_id}", status_code=303)


@app.get("/api/activities")
async def get_all_activities(admin: str = Depends(get_current_admin), db: Session = Depends(get_db)):
    """获取所有活动（仅管理员）"""
    # 从数据库获取所有活动
    db_activities = db.query(DB_Activity).all()
    
    # 转换为字典格式
    activities = []
    for activity in db_activities:
        activity_dict = {
            "id": activity.id,
            "name": activity.name,
            "description": activity.description,
            "created_at": activity.created_at.isoformat(),
            "is_active": activity.is_active
        }
        activities.append(activity_dict)
    
    return activities


@app.get("/activity/{activity_id}", response_class=HTMLResponse)
async def activity_page(request: Request, activity_id: str, db: Session = Depends(get_db)):
    """活动页面"""
    # 从数据库中查找活动
    db_activity = db.query(DB_Activity).filter(DB_Activity.id == activity_id).first()
    if not db_activity:
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error_message": "活动不存在或已被删除。",
            "activity_id": activity_id
        })
    
    # 从数据库获取roll结果，按数值倒序排序
    db_results = db.query(DB_RollResult).filter(DB_RollResult.activity_id == activity_id).order_by(DB_RollResult.number.desc()).all()
    
    # 转换活动和结果为字典格式
    activity = {
        "id": db_activity.id,
        "name": db_activity.name,
        "description": db_activity.description,
        "created_at": db_activity.created_at.isoformat(),
        "is_active": db_activity.is_active
    }
    
    results = []
    for result in db_results:
        results.append({
            "id": result.id,
            "name": result.name,
            "number": result.number,
            "ip": result.ip,
            "timestamp": result.timestamp.isoformat()
        })
    
    # 检查当前用户是否为管理员
    is_admin = False
    session_id = request.cookies.get("session_id")
    if session_id:
        # 从数据库检查会话是否有效
        session = db.query(DB_AdminSession).filter(DB_AdminSession.id == session_id).first()
        if session and datetime.now() <= session.expires_at:
            is_admin = True
    
    return templates.TemplateResponse("activity.html", {
        "request": request,
        "activity": activity,
        "results": results,
        "is_admin": is_admin
    })


@app.post("/activity/{activity_id}/roll")
async def roll_point(
    request: Request,
    activity_id: str,
    name: str = Form(...),
    db: Session = Depends(get_db)
):
    """用户参与Roll点"""
    # 从数据库中查找活动
    db_activity = db.query(DB_Activity).filter(DB_Activity.id == activity_id).first()
    if not db_activity:
        raise HTTPException(status_code=404, detail="Activity not found")
    
    # 从数据库获取roll结果，按数值倒序排序
    db_results = db.query(DB_RollResult).filter(DB_RollResult.activity_id == activity_id).order_by(DB_RollResult.number.desc()).all()
    
    # 检查当前用户是否为管理员
    is_admin = False
    session_id = request.cookies.get("session_id")
    if session_id:
        session = db.query(DB_AdminSession).filter(DB_AdminSession.id == session_id).first()
        if session and datetime.now() <= session.expires_at:
            is_admin = True
    
    # 确保活动处于活跃状态
    if not db_activity.is_active:
        # 转换活动和结果为字典格式
        activity = {
            "id": db_activity.id,
            "name": db_activity.name,
            "description": db_activity.description,
            "created_at": db_activity.created_at.isoformat(),
            "is_active": db_activity.is_active
        }
        
        results = []
        for result in db_results:
            results.append({
                "id": result.id,
                "name": result.name,
                "number": result.number,
                "ip": result.ip,
                "timestamp": result.timestamp.isoformat()
            })
        
        return templates.TemplateResponse("activity.html", {
            "request": request,
            "activity": activity,
            "results": results,
            "is_admin": is_admin,
            "error": "活动已结束，无法继续参与Roll点。"
        })
    
    # 获取用户IP地址
    # 优先从X-Forwarded-For头获取真实IP，处理多个代理的情况
    def get_client_ip(request):
        # 尝试从X-Forwarded-For头获取真实IP
        x_forwarded_for = request.headers.get('x-forwarded-for')
        if x_forwarded_for:
            # 取第一个非内网IP
            ips = [ip.strip() for ip in x_forwarded_for.split(',')]
            for ip in ips:
                # 排除内网IP和本地回环地址
                if ip and ip != '127.0.0.1' and not ip.startswith('10.') and not ip.startswith('172.16.') and not ip.startswith('192.168.'):
                    return ip
            # 如果所有都是内网IP，取第一个
            return ips[0] if ips else request.client.host
        return request.client.host
    
    client_ip = get_client_ip(request)
    
    # 检查是否已经存在该用户名的记录
    existing_result = db.query(DB_RollResult).filter(
        DB_RollResult.activity_id == activity_id,
        DB_RollResult.name == name
    ).first()
    
    if existing_result:
        # 转换活动和结果为字典格式
        activity = {
            "id": db_activity.id,
            "name": db_activity.name,
            "description": db_activity.description,
            "created_at": db_activity.created_at.isoformat(),
            "is_active": db_activity.is_active
        }
        
        results = []
        for result in db_results:
            results.append({
                "id": result.id,
                "name": result.name,
                "number": result.number,
                "ip": result.ip,
                "timestamp": result.timestamp.isoformat()
            })
        
        return templates.TemplateResponse("activity.html", {
            "request": request,
            "activity": activity,
            "results": results,
            "is_admin": is_admin,
            "error": "你已经参与过了"
        })
    
    # 移除参与次数限制，只保留名称唯一检查
    # user_participations = db.query(DB_RollResult).filter(
    #     DB_RollResult.activity_id == activity_id,
    #     DB_RollResult.name == name
    # ).count()
    
    # if user_participations >= db_activity.max_participations:
    #     # 转换活动和结果为字典格式
    #     activity = {
    #         "id": db_activity.id,
    #         "name": db_activity.name,
    #         "description": db_activity.description,
    #         "created_at": db_activity.created_at.isoformat(),
    #         "is_active": db_activity.is_active
    #     }
    #     
    #     results = []
    #     for result in db_results:
    #         results.append({
    #             "id": result.id,
    #             "name": result.name,
    #             "number": result.number,
    #             "ip": result.ip,
    #             "timestamp": result.timestamp.isoformat()
    #         })
    #     
    #     return templates.TemplateResponse("activity.html", {
    #         "request": request,
    #         "activity": activity,
    #         "results": results,
    #         "is_admin": is_admin,
    #         "error": f"您已经参与过{user_participations}次，每人最多参与{db_activity.max_participations}次。"
    #     })
    
    # 生成指定范围内不重复的随机数
    used_numbers = {result.number for result in db_results}
    available_numbers = [num for num in range(db_activity.roll_min, db_activity.roll_max + 1) if num not in used_numbers]
    
    if not available_numbers:
        # 转换活动和结果为字典格式
        activity = {
            "id": db_activity.id,
            "name": db_activity.name,
            "description": db_activity.description,
            "created_at": db_activity.created_at.isoformat(),
            "is_active": db_activity.is_active
        }
        
        results = []
        for result in db_results:
            results.append({
                "id": result.id,
                "name": result.name,
                "number": result.number,
                "ip": result.ip,
                "timestamp": result.timestamp.isoformat()
            })
        
        return templates.TemplateResponse("activity.html", {
            "request": request,
            "activity": activity,
            "results": results,
            "is_admin": is_admin,
            "error": "所有数值已经被Roll完，无法继续参与。"
        })
    
    number = random.choice(available_numbers)
    
    # 创建结果ID
    result_id = str(uuid.uuid4())
    
    # 创建数据库roll结果记录
    db_result = DB_RollResult(
        id=result_id,
        activity_id=activity_id,
        name=name,
        number=number,
        ip=client_ip,
        timestamp=datetime.now()
    )
    
    # 保存到数据库
    db.add(db_result)
    db.commit()
    
    logger.info(f"User {name} rolled {number} in activity {activity_id}")
    
    # 发送WebSocket广播，通知所有客户端有新的Roll点结果
    # 重新获取排序后的结果，计算排名
    updated_results = db.query(DB_RollResult).filter(DB_RollResult.activity_id == activity_id).order_by(DB_RollResult.number.desc()).all()
    rank = next((i + 1 for i, r in enumerate(updated_results) if r.id == result_id), 0)
    
    await manager.broadcast({
        "type": "roll_result",
        "result": {
            "id": result_id,
            "name": name,
            "number": number,
            "ip": client_ip,
            "timestamp": datetime.now().isoformat(),
            "rank": rank
        }
    }, activity_id)
    
    return RedirectResponse(url=f"/activity/{activity_id}", status_code=303)


@app.get("/api/activity/{activity_id}")
async def get_activity_data(activity_id: str, db: Session = Depends(get_db)):
    """获取活动数据的API接口"""
    # 从数据库中查找活动
    db_activity = db.query(DB_Activity).filter(DB_Activity.id == activity_id).first()
    if not db_activity:
        return JSONResponse(
            status_code=404,
            content={"detail": "活动不存在或已被删除。"}
        )
    
    # 从数据库获取roll结果，按数值倒序排序
    db_results = db.query(DB_RollResult).filter(DB_RollResult.activity_id == activity_id).order_by(DB_RollResult.number.desc()).all()
    
    # 转换活动和结果为字典格式
    activity = {
        "id": db_activity.id,
        "name": db_activity.name,
        "description": db_activity.description,
        "created_at": db_activity.created_at.isoformat(),
        "is_active": db_activity.is_active
    }
    
    results = []
    for result in db_results:
        results.append({
            "id": result.id,
            "name": result.name,
            "number": result.number,
            "ip": result.ip,
            "timestamp": result.timestamp.isoformat()
        })
    
    response_data = {
        "activity": activity,
        "results": results
    }
    
    return JSONResponse(content=response_data)


# WebSocket端点，用于实时更新Roll点结果
@app.websocket("/ws/{activity_id}")
async def websocket_endpoint(websocket: WebSocket, activity_id: str, db: Session = Depends(get_db)):
    """WebSocket端点，用于实时更新Roll点结果"""
    # 检查活动是否存在
    db_activity = db.query(DB_Activity).filter(DB_Activity.id == activity_id).first()
    if not db_activity:
        await websocket.close(code=1008, reason="活动不存在或已被删除")
        return
    
    # 接受WebSocket连接
    await manager.connect(websocket, activity_id)
    
    # 获取客户端IP（WebSocket连接中，我们只能通过accept前的headers获取IP）
    # 注意：WebSocket连接的真实IP需要在accept之前通过headers获取
    websocket_ip = "unknown"
    try:
        # 尝试从headers中获取X-Forwarded-For
        headers = websocket.headers
        x_forwarded_for = headers.get('x-forwarded-for')
        if x_forwarded_for:
            ips = [ip.strip() for ip in x_forwarded_for.split(',')]
            for ip in ips:
                if ip and ip != '127.0.0.1' and not ip.startswith('10.') and not ip.startswith('172.16.') and not ip.startswith('192.168.'):
                    websocket_ip = ip
                    break
            websocket_ip = websocket_ip if websocket_ip != "unknown" else ips[0] if ips else "unknown"
        else:
            # WebSocket连接通常没有client属性，我们只能获取到代理IP
            websocket_ip = "proxy-connection"
    except Exception as e:
        logger.debug(f"WebSocket IP获取失败: {e}")
    
    logger.info(f"WebSocket客户端连接: {activity_id} - IP: {websocket_ip}")
    
    try:
        while True:
            # 接收客户端消息（当前不需要处理客户端消息）
            await websocket.receive_text()
    except WebSocketDisconnect:
        # 处理客户端断开连接
        logger.info(f"WebSocket客户端断开: {activity_id} - IP: {websocket_ip}")
        manager.disconnect(websocket, activity_id)
    except Exception as e:
        # 处理其他异常
        logger.error(f"WebSocket错误: {e} - IP: {websocket_ip}")
        manager.disconnect(websocket, activity_id)
    finally:
        # 确保连接被正确断开
        manager.disconnect(websocket, activity_id)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8803)
