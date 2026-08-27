from __future__ import annotations
import json
from pathlib import Path
import httpx
from collectors.app_store import resolve_app_store_id
from collectors.google_play import resolve_google_play_id
from storage.state import StateStore

async def resolve_all_sources(sources_cfg: dict, out_path: Path | None = None, state: StateStore | None = None) -> dict:
    wallets = sources_cfg.get("competitor",{}).get("wallets",[])
    results = {}
    async with httpx.AsyncClient(follow_redirects=True, timeout=8) as client:
        for w in wallets:
            name = w["name"]
            expected_domain = w.get("official_website","").replace("https://","").replace("http://","").split("/")[0]
            # App Store
            app_name = w.get("app_store_name") or name
            a_res = await resolve_app_store_id(client, app_name, expected_domain)
            # Google Play
            pkg = w.get("google_play_id")
            g_res = await resolve_google_play_id(client, app_name, pkg)
            results[w["slug"]] = {
                "name": name,
                "app_store": a_res,
                "google_play": g_res,
                "official_website": w.get("official_website"),
            }
            # incremental save
            if state is not None:
                state.save_resolved(results)
            elif out_path is not None:
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_text(json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    return results
