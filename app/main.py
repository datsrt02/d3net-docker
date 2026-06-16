from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from .config import AppConfig, load_config, save_config
from .d3net_service import D3netRuntime

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="Daikin DIII-Net Docker Modbus Server")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
runtime = D3netRuntime()


class PowerRequest(BaseModel):
    power: bool


class ModeRequest(BaseModel):
    mode: str


class SetpointRequest(BaseModel):
    setpoint: float


class FanSpeedRequest(BaseModel):
    speed: str


class FanDirectionRequest(BaseModel):
    direction: str


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request, "config": load_config()})


@app.get("/api/config")
async def api_get_config() -> dict[str, Any]:
    return load_config().model_dump()


@app.post("/api/config")
async def api_set_config(config: AppConfig) -> dict[str, Any]:
    save_config(config)
    return {"ok": True, "config": config.model_dump()}


@app.post("/api/start")
async def api_start() -> dict[str, Any]:
    try:
        await runtime.start(load_config())
        return {"ok": True, **runtime.status_json()}
    except Exception as exc:
        runtime.last_error = str(exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/stop")
async def api_stop() -> dict[str, Any]:
    await runtime.stop()
    return {"ok": True, **runtime.status_json()}


@app.post("/api/poll")
async def api_poll() -> dict[str, Any]:
    try:
        await runtime.poll_once()
        return {"ok": True, **runtime.status_json()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/status")
async def api_status() -> dict[str, Any]:
    return runtime.status_json()


@app.get("/api/units")
async def api_units() -> list[dict[str, Any]]:
    return runtime.units_json()


@app.get("/api/unit/{unit_id}")
async def api_unit(unit_id: str) -> dict[str, Any]:
    for unit in runtime.units_json():
        if unit["id"] == unit_id:
            return unit
    raise HTTPException(status_code=404, detail="Unit not found")


@app.post("/api/unit/{unit_id}/power")
async def api_power(unit_id: str, body: PowerRequest) -> dict[str, Any]:
    await runtime.set_power(unit_id, body.power)
    return {"ok": True}


@app.post("/api/unit/{unit_id}/mode")
async def api_mode(unit_id: str, body: ModeRequest) -> dict[str, Any]:
    await runtime.set_mode(unit_id, body.mode)
    return {"ok": True}


@app.post("/api/unit/{unit_id}/setpoint")
async def api_setpoint(unit_id: str, body: SetpointRequest) -> dict[str, Any]:
    await runtime.set_setpoint(unit_id, body.setpoint)
    return {"ok": True}


@app.post("/api/unit/{unit_id}/fan-speed")
async def api_fan_speed(unit_id: str, body: FanSpeedRequest) -> dict[str, Any]:
    await runtime.set_fan_speed(unit_id, body.speed)
    return {"ok": True}


@app.post("/api/unit/{unit_id}/fan-direction")
async def api_fan_direction(unit_id: str, body: FanDirectionRequest) -> dict[str, Any]:
    await runtime.set_fan_direction(unit_id, body.direction)
    return {"ok": True}
