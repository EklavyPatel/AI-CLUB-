"""Vercel FastAPI UI/PDF service with a private Cloudflare Worker + D1 backend."""
import io
import os
from contextlib import asynccontextmanager
from http.cookiejar import CookieJar, DefaultCookiePolicy
from pathlib import Path

import httpx
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pypdf import PdfReader

from .pdf_parser import parse_questions

STATIC = Path(__file__).resolve().parents[1] / 'static'


class RejectBackendCookies(DefaultCookiePolicy):
    def set_ok(self, cookie, request):
        return False


@asynccontextmanager
async def lifespan(app):
    # Reuse connections, but never share a backend cookie jar between students.
    async with httpx.AsyncClient(
        http2=True, timeout=httpx.Timeout(45, connect=15, pool=30),
        limits=httpx.Limits(max_connections=300, max_keepalive_connections=100),
        cookies=CookieJar(policy=RejectBackendCookies()),
    ) as client:
        app.state.backend_client = client
        yield


app = FastAPI(title='Beyond the Number · College assessments', version='4.0.0', lifespan=lifespan)
app.mount('/static', StaticFiles(directory=STATIC), name='static')


def backend_headers(request):
    return {'Authorization': 'Bearer '+os.environ['D1_GATEWAY_TOKEN'],
            'Cookie': request.headers.get('cookie', ''),
            'Content-Type': request.headers.get('content-type', 'application/json'),
            'x-site-protocol': request.headers.get('x-forwarded-proto', request.url.scheme).split(',')[0],
            'x-client-ip': request.headers.get('x-forwarded-for', request.client.host if request.client else '').split(',')[0]}


@app.middleware('http')
async def protect(request, call_next):
    if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'}:
        origin = request.headers.get('origin')
        protocol = request.headers.get('x-forwarded-proto', request.url.scheme).split(',')[0]
        if origin and origin != f'{protocol}://{request.url.netloc}':
            return JSONResponse({'detail': 'Cross-origin writes are not allowed.'}, status_code=403)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
    return response


@app.get('/')
def index():
    return FileResponse(STATIC/'index.html')


@app.post('/api/question-bank/import-pdf')
async def import_pdf(request: Request, file: UploadFile = File(...)):
    try:
        auth = await request.app.state.backend_client.get(os.environ['D1_GATEWAY_URL']+'/api/auth/me', headers=backend_headers(request))
    except httpx.RequestError:
        raise HTTPException(503, 'The assessment service is temporarily unavailable.')
    if auth.status_code != 200:
        return Response(auth.content, status_code=auth.status_code, media_type='application/json')
    if auth.json()['role'] != 'teacher':
        raise HTTPException(403, 'Only teachers can import question banks.')
    content = await file.read(3*1024*1024+1)
    if len(content) > 3*1024*1024:
        raise HTTPException(413, 'Choose a PDF smaller than 3 MB.')
    if not content.startswith(b'%PDF-'):
        raise HTTPException(422, 'Upload a valid PDF document.')
    try:
        reader = PdfReader(io.BytesIO(content))
        if reader.is_encrypted:
            raise ValueError('Remove password protection before importing.')
        if len(reader.pages) > 100:
            raise ValueError('Import at most 100 PDF pages.')
        items = parse_questions('\n'.join(page.extract_text() or '' for page in reader.pages))
    except Exception as exc:
        raise HTTPException(422, str(exc) if isinstance(exc, ValueError) else 'This PDF could not be read. Export a text PDF and try again.')
    return {'items': items, 'count': len(items), 'message': 'Review every question and correct answer before publishing.'}


@app.api_route('/api/{path:path}', methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE'])
async def proxy(path: str, request: Request):
    content = bytearray()
    async for chunk in request.stream():
        content.extend(chunk)
        if len(content) > 3*1024*1024:
            raise HTTPException(413, 'Request is too large.')
    try:
        result = await request.app.state.backend_client.request(request.method, os.environ['D1_GATEWAY_URL']+'/api/'+path,
                                      headers=backend_headers(request), content=bytes(content))
    except httpx.RequestError:
        raise HTTPException(503, 'The assessment service is temporarily unavailable. Please retry.')
    response = Response(result.content, status_code=result.status_code,
                        media_type='application/json')
    for cookie in result.headers.get_list('set-cookie'):
        response.headers.append('set-cookie', cookie)
    return response
