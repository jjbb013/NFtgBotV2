import asyncio
import secrets
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import Depends, FastAPI, HTTPException, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import config
import telegram_client
from core import processor

security = HTTPBasic(auto_error=False)


def verify(credentials):
    if not credentials:
        raise HTTPException(status_code=401, headers={"WWW-Authenticate": "Basic"})
    correct = secrets.compare_digest(credentials.username, config.DASHBOARD_USERNAME) and \
              secrets.compare_digest(credentials.password, config.DASHBOARD_PASSWORD)
    if not correct:
        raise HTTPException(status_code=401, headers={"WWW-Authenticate": "Basic"})


async def get_current_user(credentials: HTTPBasicCredentials = Depends(security)):
    verify(credentials)
    return credentials.username


@asynccontextmanager
async def lifespan(app: FastAPI):
    telegram_task = asyncio.create_task(telegram_client.start_client())
    app.state.startup_time = datetime.utcnow().isoformat()
    app.state.telegram_task = telegram_task
    yield
    telegram_task.cancel()
    try:
        await telegram_task
    except asyncio.CancelledError:
        pass
    if telegram_client.client:
        await telegram_client.client.disconnect()


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="web/templates")


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "telegram_connected": telegram_client.is_connected(),
        "startup_time": getattr(app.state, 'startup_time', None),
    }


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, user: str = Depends(get_current_user)):
    accounts = telegram_client.accounts
    return templates.TemplateResponse("index.html", {
        "request": request,
        "accounts": [a.name for a in accounts],
        "telegram_connected": telegram_client.is_connected(),
        "startup_time": getattr(app.state, 'startup_time', None),
        "logs": list(processor.log_buffer)[-50:],
    })


@app.get("/orders", response_class=HTMLResponse)
async def orders_page(request: Request, user: str = Depends(get_current_user)):
    return templates.TemplateResponse("orders.html", {"request": request})


@app.get("/api/orders")
async def api_orders(account_idx: int = Query(1), symbol: str = Query("BTC"), user: str = Depends(get_current_user)):
    account = next((a for a in telegram_client.accounts if a.idx == account_idx), None)
    if not account:
        raise HTTPException(status_code=404, detail="账户不存在")
    data = account.get_orders(symbol)
    return {"account": account.name, "symbol": symbol, "orders": data}


@app.get("/logs")
async def logs(user: str = Depends(get_current_user)):
    return {"logs": list(processor.log_buffer)}


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})


@app.post("/api/login/start")
async def api_login_start(payload: dict):
    phone = payload.get("phone")
    if not phone:
        raise HTTPException(status_code=400, detail="phone 必填")
    result = await telegram_client.start_login(phone)
    return JSONResponse(result)


@app.post("/api/login/confirm")
async def api_login_confirm(payload: dict):
    phone = payload.get("phone")
    code = payload.get("code")
    if not phone or not code:
        raise HTTPException(status_code=400, detail="phone 和 code 必填")
    result = await telegram_client.confirm_login(phone, code)
    return JSONResponse(result)
