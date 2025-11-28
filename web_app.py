import json
import logging
import os
from pathlib import Path

from aiohttp import web

from main import generate_lua_for_app, search_game_info

log = logging.getLogger(__name__)


ROOT = Path(__file__).parent
STATIC_DIR = ROOT / "static"


def create_app():
    app = web.Application()

    async def index(_):
        return web.FileResponse(STATIC_DIR / "index.html")

    async def search(request: web.Request):
        query = request.query.get("q", "").strip()
        if not query:
            return web.json_response({"error": "缺少搜索内容"}, status=400)

        games = await search_game_info(query)
        simplified = [
            {
                "appid": str(game.get("appid", "")),
                "name": game.get("name", ""),
                "schinese_name": game.get("schinese_name", ""),
            }
            for game in games
        ]
        return web.json_response({"results": simplified})

    async def fetch_manifest(request: web.Request):
        try:
            payload = await request.json()
        except json.JSONDecodeError:
            return web.json_response({"error": "请求体必须是JSON"}, status=400)

        user_input = (payload.get("appid") or payload.get("query") or "").strip()
        preferred_name = (payload.get("gameName") or "").strip() or None

        if not user_input:
            return web.json_response({"error": "请输入有效的 AppID 或游戏名"}, status=400)

        log.info("收到清单请求: %s", user_input)
        result = await generate_lua_for_app(user_input, preferred_name)
        if not result:
            return web.json_response({"error": "未找到匹配的游戏或清单下载失败"}, status=404)

        return web.json_response(result)

    app.router.add_get("/", index)
    app.router.add_get("/api/search", search)
    app.router.add_post("/api/fetch", fetch_manifest)
    app.router.add_static("/static/", path=str(STATIC_DIR), show_index=False)
    return app


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    web.run_app(create_app(), port=int(os.getenv("PORT", 8000)))
