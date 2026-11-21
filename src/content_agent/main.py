import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from content_agent.live_session import LiveSession, LiveSessionError
from content_agent.pipeline import analyze_async
from content_agent.schemas import (
    AgentInput,
    AgentOutput,
    LiveConfigUpdate,
    LiveMetricsUpdate,
    LiveStartRequest,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
STATIC_DIR = Path(__file__).resolve().parent / "static"
SCENE_FILES = (
    ("scene", "标准讲解场景", "产品讲解期 · 油皮 / 价格 / 小样 · 规则版基线", "scene.json"),
    (
        "conflict",
        "促单冲突场景",
        "促单期 · 同问与负面反馈 · 触发答疑插播",
        "scene_conflict.json",
    ),
)

app = FastAPI(title="ContentAgent Live Assistant", version="0.1.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
live_session = LiveSession()


def _load_products() -> list[dict[str, Any]]:
    try:
        data = json.loads(
            (PROJECT_ROOT / "config" / "products.json").read_text(encoding="utf-8-sig")
        )
    except (OSError, json.JSONDecodeError):
        return []
    return [
        {
            "sku_id": item.get("sku_id", ""),
            "name": item.get("name", ""),
            "specification": item.get("specification", ""),
            "price": item.get("price"),
            "ingredients": item.get("ingredients", []),
            "benefits": item.get("benefits", []),
        }
        for item in data.get("products", [])
        if item.get("sku_id") and item.get("name")
    ]


def _load_stages() -> list[dict[str, Any]]:
    try:
        data = json.loads(
            (PROJECT_ROOT / "config" / "decision_rules.json").read_text(
                encoding="utf-8-sig"
            )
        )
    except (OSError, json.JSONDecodeError):
        return []
    return [
        {
            "name": stage.get("name", ""),
            "start_ratio": stage.get("start_ratio", 0),
            "end_ratio": stage.get("end_ratio", 1),
            "focus": stage.get("focus", ""),
            "goal": stage.get("goal", ""),
        }
        for stage in data.get("stages", [])
    ]


@app.get("/", include_in_schema=False)
@app.get("/demo", include_in_schema=False)
def demo_page() -> FileResponse:
    return FileResponse(
        STATIC_DIR / "index.html",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/compliance", include_in_schema=False)
def compliance_page() -> FileResponse:
    return FileResponse(
        STATIC_DIR / "compliance.html",
        headers={"Cache-Control": "no-store"},
    )


@app.get("/compliance/rules")
def compliance_rules() -> dict[str, Any]:
    try:
        return json.loads(
            (PROJECT_ROOT / "config" / "compliance_rules.json").read_text(
                encoding="utf-8-sig"
            )
        )
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=500, detail="合规词库加载失败") from exc


@app.get("/demo/bootstrap")
def demo_bootstrap() -> dict[str, Any]:
    """Return the stage plan and preset scenes used by the web demo."""
    scenes: list[dict[str, Any]] = []
    for scene_id, name, description, filename in SCENE_FILES:
        try:
            scene = json.loads(
                (PROJECT_ROOT / "examples" / filename).read_text(encoding="utf-8-sig")
            )
        except (OSError, json.JSONDecodeError):
            continue
        scenes.append(
            {
                "id": scene_id,
                "name": name,
                "description": description,
                "scene": scene,
            }
        )
    return {
        "stages": _load_stages(),
        "scenes": scenes,
        "products": _load_products(),
    }


@app.get("/live/status")
def live_status() -> dict[str, Any]:
    return live_session.status_payload()


@app.post("/live/start")
async def live_start(config: LiveStartRequest | None = None) -> dict[str, Any]:
    try:
        return await live_session.start(config)
    except LiveSessionError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/live/stop")
async def live_stop() -> dict[str, Any]:
    return await live_session.stop()


@app.post("/live/config")
def live_config(update: LiveConfigUpdate) -> dict[str, Any]:
    try:
        return live_session.update_config(update)
    except LiveSessionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/live/metrics")
def live_metrics(update: LiveMetricsUpdate) -> dict[str, Any]:
    return live_session.update_metrics(update)


@app.post("/live/analyze")
async def live_analyze() -> dict[str, Any]:
    try:
        output = await live_session.analyze_now()
    except LiveSessionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    status = live_session.status_payload()
    return {
        "analysis": output.model_dump() if output else None,
        "message": "" if output else "本窗口暂无弹幕",
        "at": status["last_analysis_at"],
        "window_seconds": status["window_seconds"],
    }


@app.get("/live/events")
async def live_events(request: Request) -> StreamingResponse:
    return StreamingResponse(
        live_session.stream(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/analyze", response_model=AgentOutput)
async def analyze_scene(payload: AgentInput) -> AgentOutput:
    return await analyze_async(payload)
