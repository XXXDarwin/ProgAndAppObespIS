# iot_server/main.py
from fastapi import FastAPI

from api.routes import router

app = FastAPI(title='IoT Warehouse Server')
app.include_router(router, prefix='/api/v1')


@app.get('/health')
def health():
    return {'status': 'ok'}