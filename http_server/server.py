# http/server.py
from aiohttp import web
import uuid

async def handle_ping(_):
    return web.Response(text="pong")

def make_app(db_pool):
    app = web.Application()
    app["db_pool"] = db_pool

    async def handle_get_image(request):
        media_id = request.match_info.get("id","").split(".",1)[0]
        try: uuid.UUID(media_id)
        except Exception: return web.Response(status=404, text="not found")

        row = await app["db_pool"].fetchrow("SELECT mime, bytes FROM media WHERE id = $1", uuid.UUID(media_id))
        if not row:
            return web.Response(status=404, text="not found")
        return web.Response(body=bytes(row["bytes"]), content_type=row["mime"], headers={
            "Cache-Control": "public, max-age=31536000, immutable",
            "ETag": media_id,
            "Content-Disposition": 'inline; filename="image.png"',
        })

    app.router.add_get("/", handle_ping)
    app.router.add_get("/i/{id}", handle_get_image)
    return app

async def start_http_server(port: int, db_pool):
    app = make_app(db_pool)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    return runner

async def stop_http_server(runner):
    await runner.cleanup()
