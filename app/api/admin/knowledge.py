"""管理端：知识库文档上传、全量重建索引。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, UploadFile

from app.api.admin import require_admin
from app.rag.indexer import ingest_document, rebuild_all

router = APIRouter()


@router.post("/admin/knowledge/upload")
async def upload(file: UploadFile = File(...), doc_id: str = Form(...), title: str = Form(...),
                 _admin=Depends(require_admin)):
    content = await file.read()
    result = ingest_document(doc_id, title, file.filename or "upload.md", content)
    return result


@router.post("/admin/knowledge/rebuild")
async def rebuild(_admin=Depends(require_admin)):
    return rebuild_all()
