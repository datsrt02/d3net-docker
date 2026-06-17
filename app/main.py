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
from .knx_service import KnxConfig, KnxMapping, MonitorRequest, KnxRuntime

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="Daikin DIII-Net Docker Modbus Server")
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))
runtime = D3netRuntime()
knx_runtime = KnxRuntime()


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
    try:
        return await runtime.units_json_async()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/unit/{unit_id}")
async def api_unit(unit_id: str) -> dict[str, Any]:
    for unit in await runtime.units_json_async():
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


@app.get("/api/debug/system")
async def api_debug_system() -> dict[str, Any]:
    try:
        return await runtime.debug_system_registers()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/debug/unit/{unit_id}")
async def api_debug_unit(unit_id: str) -> dict[str, Any]:
    try:
        return await runtime.debug_unit_registers(unit_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/knx/config")
async def api_knx_get_config() -> dict[str, Any]:
    cfg = load_config()
    return {
        "gateway_name": cfg.knx_gateway_name,
        "gateway_ip": cfg.knx_gateway_ip,
        "gateway_port": cfg.knx_gateway_port,
        "physical_address": cfg.knx_physical_address,
        "protocol": cfg.knx_protocol,
    }


@app.post("/api/knx/config")
async def api_knx_set_config(config: KnxConfig) -> dict[str, Any]:
    cfg = load_config()
    cfg.knx_gateway_name = config.gateway_name
    cfg.knx_gateway_ip = config.gateway_ip
    cfg.knx_gateway_port = config.gateway_port
    cfg.knx_physical_address = config.physical_address
    cfg.knx_protocol = config.protocol
    save_config(cfg)
    knx_runtime.set_config(config)
    return {"ok": True, "config": config.model_dump()}


@app.post("/api/knx/connect")
async def api_knx_connect(config: KnxConfig | None = None) -> dict[str, Any]:
    if config is None:
        data = await api_knx_get_config()
        config = KnxConfig(**data)
    await api_knx_set_config(config)
    await knx_runtime.connect(config)
    return {"ok": True, **knx_runtime.status_json()}


@app.post("/api/knx/disconnect")
async def api_knx_disconnect() -> dict[str, Any]:
    await knx_runtime.disconnect()
    return {"ok": True, **knx_runtime.status_json()}


@app.get("/api/knx/status")
async def api_knx_status() -> dict[str, Any]:
    return knx_runtime.status_json()


@app.post("/api/knx/monitor")
async def api_knx_monitor(body: MonitorRequest) -> dict[str, Any]:
    knx_runtime.set_monitor(body.enabled)
    return {"ok": True, **knx_runtime.status_json()}


@app.get("/api/knx/logs")
async def api_knx_logs(limit: int = 100, ga_filter: str | None = None) -> list[dict[str, Any]]:
    return knx_runtime.logs_json(limit=limit, ga_filter=ga_filter)


@app.post("/api/knx/logs/clear")
async def api_knx_clear_logs() -> dict[str, Any]:
    knx_runtime.clear_logs()
    return {"ok": True}


@app.get("/api/knx/mappings")
async def api_knx_mappings() -> list[dict[str, Any]]:
    return knx_runtime.mappings_json()


@app.post("/api/knx/mappings")
async def api_knx_save_mapping(mapping: KnxMapping) -> dict[str, Any]:
    knx_runtime.save_mapping(mapping)
    return {"ok": True, "mappings": knx_runtime.mappings_json()}
