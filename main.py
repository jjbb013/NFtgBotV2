import uvicorn
import config

if __name__ == '__main__':
    uvicorn.run(
        'web.app:app',
        host='0.0.0.0',
        port=config.DASHBOARD_PORT,
        workers=1,
        loop='asyncio',
        log_config=None,
    )
