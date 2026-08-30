"""知识库管理 API（LLM-WIKI 式：多级文件夹 + 文档上传解析，无需权限）。

端点一览：
- GET    /api/knowledge/tree         知识库树（文件夹 + 文档）
- POST   /api/knowledge/folder       新建文件夹 {name, parent}
- PUT    /api/knowledge/folder       重命名文件夹 {path, name}
- DELETE /api/knowledge/folder       删除文件夹 ?path=
- POST   /api/knowledge/upload       上传文档（multipart：file + folder）
- PUT    /api/knowledge/doc/{id}     重命名文档 {name}
- DELETE /api/knowledge/doc/{id}     删除文档
- GET    /api/knowledge/doc/{id}/content  文档 Markdown 内容
- GET    /api/knowledge/doc/{id}/raw      原始文件下载
- GET    /api/knowledge/search            全文检索 ?q=
"""
from __future__ import annotations

import os
from typing import Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from ..services import knowledge_service as kb

router = APIRouter(prefix='/api/knowledge', tags=['knowledge'])


def _json(payload: dict) -> JSONResponse:
    return JSONResponse(payload)


@router.get('/tree')
def tree():
    return _json(kb.list_tree())


@router.post('/folder')
def create_folder(body: dict):
    name = str(body.get('name', '')).strip()
    parent = str(body.get('parent', '') or '').strip()
    return _json(kb.create_folder(name, parent))


@router.put('/folder')
def rename_folder(body: dict):
    path = str(body.get('path', '') or '').strip()
    name = str(body.get('name', '')).strip()
    return _json(kb.rename_folder(path, name))


@router.delete('/folder')
def delete_folder(path: str):
    return _json(kb.delete_folder(path or ''))


@router.post('/upload')
async def upload(file: UploadFile = File(...), folder: str = Form('')):
    try:
        data = await file.read()
    except Exception as e:
        return _json({'ok': False, 'error': f'读取上传文件失败：{e}'})
    if not data:
        return _json({'ok': False, 'error': '文件内容为空'})
    return _json(kb.upload(file.filename or '未命名', data, folder or ''))


@router.put('/doc/{doc_id}')
def rename_doc(doc_id: str, body: dict):
    return _json(kb.rename_doc(doc_id, str(body.get('name', '')).strip()))


@router.delete('/doc/{doc_id}')
def delete_doc(doc_id: str):
    return _json(kb.delete_doc(doc_id))


@router.get('/doc/{doc_id}/content')
def doc_content(doc_id: str):
    return _json(kb.doc_content(doc_id))


@router.get('/doc/{doc_id}/raw')
def doc_raw(doc_id: str):
    doc = kb.get_doc(doc_id)
    if not doc:
        raise HTTPException(status_code=404, detail='文档不存在')
    raw = doc.get('raw')
    if not raw:
        raise HTTPException(status_code=404, detail='该文档没有原始文件')
    path = os.path.join(kb.kb_root(), raw)
    if not os.path.isfile(path):
        raise HTTPException(status_code=404, detail='原始文件已丢失')
    return FileResponse(path, filename=doc.get('original') or doc.get('title') + (doc.get('ext') or ''))


@router.get('/search')
def search(q: Optional[str] = ''):
    return _json(kb.search(q or ''))
