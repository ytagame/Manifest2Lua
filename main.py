import asyncio
import logging
import os
from typing import List, Optional, Tuple

import aiofiles
import aiohttp
import vdf

# 设置日志
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# 定义全局变量
repos = [
    "SteamAutoCracks/ManifestHub",
    "ikun0014/ManifestHub",
    "Auiowu/ManifestAutoUpdate",
]

# 错误处理函数
def stack_error(e):
    return f"{type(e).__name__}: {e}"

# 从SteamUI搜索游戏信息
async def search_game_info(search_term: str):
    url = f"https://steamui.com/loadGames.php?search={search_term}"
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, ssl=False) as r:
                if r.status == 200:
                    try:
                        data = await r.json()
                        games = data.get('games', [])
                        return games
                    except aiohttp.ContentTypeError:
                        log.error(f"⚠ 获取游戏信息失败: 响应不是JSON格式 (AppID: {search_term})")
                        return []
                else:
                    log.error(f"⚠ 获取游戏信息失败: 状态码 {r.status} (AppID: {search_term})")
                    return []
        except aiohttp.ClientError as e:
            log.error(f"⚠ 获取游戏信息失败: 连接错误 {e} (AppID: {search_term})")
            return []

# 通过游戏名查找appid
async def find_appid_by_name(game_name: str, selection_index: Optional[int] = None):
    games = await search_game_info(game_name)
    if games:
        if selection_index is None:
            print("🔍 找到以下匹配的游戏:")
            for idx, game in enumerate(games, 1):
                # 使用schinese_name，如果为空则使用name
                game_name_display = game["schinese_name"] if game["schinese_name"] else game["name"]
                print(f"{idx}. {game_name_display} (AppID: {game['appid']})")
            choice = input("请选择游戏编号：")
            if choice.isdigit() and 1 <= int(choice) <= len(games):
                selection_index = int(choice) - 1
            else:
                log.error("⚠ 未找到匹配的游戏")
                return None, None

        if 0 <= selection_index < len(games):
            selected_game = games[selection_index]
            game_name_display = selected_game["schinese_name"] if selected_game["schinese_name"] else selected_game["name"]
            log.info(f"✅ 选择的游戏: {game_name_display} (AppID: {selected_game['appid']})")
            return str(selected_game["appid"]), game_name_display

    log.error("⚠ 未找到匹配的游戏")
    return None, None

# 通过appid获取游戏名
async def get_game_name_by_appid(appid: str):
    games = await search_game_info(appid)
    if games:
        game = games[0]  # 获取第一个匹配的游戏
        game_name = game['schinese_name'] if game['schinese_name'] else game['name']
        log.info(f"✅ 通过AppID找到游戏名: {game_name}")
        return game_name
    else:
        log.warning(f"⚠ 未通过AppID找到游戏名")
        return ""


# 异步函数从多个URL下载文件
async def get(sha: str, path: str, repo: str):
    url_list = [
        f"https://jsdelivr.pai233.top/gh/{repo}@{sha}/{path}",
        f"https://cdn.jsdmirror.com/gh/{repo}@{sha}/{path}",
        f"https://raw.gitmirror.com/{repo}/{sha}/{path}",
        f"https://raw.dgithub.xyz/{repo}/{sha}/{path}",
        f"https://gh.akass.cn/{repo}/{sha}/{path}",
    ]
    retry = 3
    async with aiohttp.ClientSession() as session:
        while retry:
            for url in url_list:
                try:
                    async with session.get(url, ssl=False) as r:
                        if r.status == 200:
                            return await r.read()
                        else:
                            log.error(f'🔄 获取失败: {path} - 状态码: {r.status}')
                except aiohttp.ClientError:
                    log.error(f'🔄 获取失败: {path} - 连接错误')
            retry -= 1
            log.warning(f'🔄 重试剩余次数: {retry} - {path}')
    log.error(f'🔄 超过最大重试次数: {path}')
    return None  # 如果下载失败，返回None

# 异步函数获取manifest数据并收集depot信息
async def get_manifest(sha: str, path: str, save_dir: str, repo: str):
    collected_depots: List[Tuple[str, str]] = []
    try:
        if path.endswith('.manifest'):
            save_path = os.path.join(save_dir, path)
            if os.path.exists(save_path):
                log.warning(f'👋 已存在清单: {path}')
                return collected_depots
            content = await get(sha, path, repo)
            if content:
                log.info(f'🔄 清单下载成功: {path}')
                # 保存manifest文件
                async with aiofiles.open(save_path, 'wb') as f:
                    await f.write(content)
        # 尝试下载Key.vdf或config.vdf
        elif path in ['Key.vdf', 'key.vdf', 'config.vdf']:
            content = await get(sha, path, repo)
            if content:
                log.info(f'🔄 密钥下载成功: {path}')
                depots_config = vdf.loads(content.decode(encoding='utf-8'))
                for depot_id, depot_info in depots_config['depots'].items():
                    collected_depots.append((depot_id, depot_info['DecryptionKey']))
    except KeyboardInterrupt:
        raise
    except Exception as e:
        log.error(f'处理失败: {path} - {stack_error(e)}')
        raise
    return collected_depots

# 异步主函数组织下载和处理
async def download_and_process(app_id: str, game_name: str):
    app_id_list = list(filter(str.isdecimal, app_id.strip().split("-")))
    app_id = app_id_list[0]
    # 创建保存manifest和Lua文件的目录
    save_dir = f"[{app_id}]{game_name}"
    os.makedirs(save_dir, exist_ok=True)
    # 遍历每个仓库
    for repo in repos:
        log.info(f"🔍 搜索仓库: {repo}")
        url = f"https://api.github.com/repos/{repo}/branches/{app_id}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, ssl=False) as r:
                r_json = await r.json()
                if "commit" in r_json:
                    sha = r_json["commit"]["sha"]
                    tree_url = r_json["commit"]["commit"]["tree"]["url"]
                    date = r_json["commit"]["commit"]["author"]["date"]
                    async with session.get(tree_url, ssl=False) as r2:
                        r2_json = await r2.json()
                        if "tree" in r2_json:
                            collected_depots: List[Tuple[str, str]] = []
                            vdf_paths = ["Key.vdf", "key.vdf", "config.vdf"]
                            # 优先处理VDF文件
                            for item in r2_json["tree"]:
                                if item["path"] in vdf_paths:
                                    vdf_result = await get_manifest(sha, item["path"], save_dir, repo)
                                    if vdf_result:
                                        collected_depots.extend(vdf_result)
                                        # 找到第一个匹配的VDF就停止查找
                                        break

                            # 处理manifest文件
                            for item in r2_json["tree"]:
                                if item["path"].endswith(".manifest"):
                                    result = await get_manifest(sha, item["path"], save_dir, repo)
                                    collected_depots.extend(result)

                            if collected_depots:
                                log.info(f"✅ 清单最后更新时间：{date}")
                                log.info(f"✅ 入库成功: {app_id} 在仓库 {repo}")
                                return collected_depots, save_dir, date
        log.warning(f"⚠ 游戏未在仓库 {repo} 中找到。继续搜索下一个仓库。")
    log.error(f"⚠ 清单下载失败: {app_id} 在所有仓库中")
    return [], save_dir, None

# 解析VDF文件生成Lua脚本
def parse_vdf_to_lua(depot_info: List[Tuple[str, str]], appid: str, save_dir: str):
    lua_lines: List[str] = []
    # 将appid添加到Lua脚本中
    lua_lines.append(f'addappid({appid})')
    for depot_id, decryption_key in depot_info:
        lua_lines.append(f'addappid({depot_id},1,"{decryption_key}")')
        # 查找depot的所有manifest文件
        manifest_files = [f for f in os.listdir(save_dir) if f.startswith(depot_id + "_") and f.endswith(".manifest")]
        for manifest_file in manifest_files:
            manifest_id = manifest_file[len(depot_id) + 1:-len(".manifest")]
            lua_lines.append(f'setManifestid({depot_id},"{manifest_id}",0)')
    return "\n".join(lua_lines)


def summarize_depots(depot_info: List[Tuple[str, str]], save_dir: str):
    summary = []
    for depot_id, decryption_key in depot_info:
        manifest_files = [f for f in os.listdir(save_dir) if f.startswith(depot_id + "_") and f.endswith(".manifest")]
        manifest_ids = [f[len(depot_id) + 1 : -len(".manifest")] for f in manifest_files]
        summary.append(
            {
                "depot_id": depot_id,
                "decryption_key": decryption_key,
                "manifest_ids": manifest_ids,
            }
        )
    return summary


async def resolve_appid_and_name(user_input: str, preferred_name: Optional[str] = None):
    stripped = user_input.strip()
    if stripped.isdigit():
        appid = stripped
        game_name = preferred_name or await get_game_name_by_appid(appid)
        return appid, game_name

    games = await search_game_info(stripped)
    if not games:
        log.error("⚠ 未找到匹配的游戏")
        return None, None

    selected_game = games[0]
    game_name = preferred_name or selected_game.get("schinese_name") or selected_game.get("name")
    return str(selected_game.get("appid", "")), game_name


async def generate_lua_for_app(user_input: str, preferred_name: Optional[str] = None):
    appid, game_name = await resolve_appid_and_name(user_input, preferred_name)
    if not appid:
        return None

    collected_depots, save_dir, last_updated = await download_and_process(appid, game_name or appid)
    if not collected_depots:
        return None

    lua_script = parse_vdf_to_lua(collected_depots, appid, save_dir)
    depot_summary = summarize_depots(collected_depots, save_dir)
    return {
        "appid": appid,
        "game_name": game_name,
        "save_dir": save_dir,
        "lua_script": lua_script,
        "depots": depot_summary,
        "last_updated": last_updated,
    }

# 主函数运行整个流程
def main():
    user_input = input("请输入appid或游戏名：").strip()

    result = asyncio.run(generate_lua_for_app(user_input))
    if not result:
        print("未找到匹配的游戏或清单下载失败。请尝试其他名称。")
        return

    appid = result["appid"]
    game_name = result["game_name"] or appid
    save_dir = result["save_dir"]
    lua_script = result["lua_script"]

    lua_file_path = os.path.join(save_dir, f"{appid}.lua")
    with open(lua_file_path, "w", encoding="utf-8") as lua_file:
        lua_file.write(lua_script)

    print(f"生成 {game_name} 解锁文件成功")
    print(f"将 {save_dir} 文件夹内所有文件拖动到 steamtools 的悬浮窗上")
    print(f"并按提示关闭 steam 后重新打开即可下载游玩 {game_name}")

if __name__ == "__main__":
    main()
    input("按任意键退出...")
