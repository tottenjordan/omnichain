"""Endpoints for browsing and creating GCS folders."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from omnichain.services.gcs_service import GcsService, get_gcs_service

router = APIRouter(prefix="/api/gcs", tags=["gcs"])

GcsDep = Annotated[GcsService, Depends(get_gcs_service)]


class FoldersResponse(BaseModel):
    bucket: str
    folders: list[str]


class CreateFolderRequest(BaseModel):
    bucket: str
    folder: str


class CreateFolderResponse(BaseModel):
    bucket: str
    folder: str


@router.get("/folders", response_model=FoldersResponse)
def list_folders(bucket: str, svc: GcsDep) -> FoldersResponse:
    return FoldersResponse(bucket=bucket, folders=svc.list_folders(bucket))


@router.post("/folders", status_code=201, response_model=CreateFolderResponse)
def create_folder(req: CreateFolderRequest, svc: GcsDep) -> CreateFolderResponse:
    created = svc.create_folder(req.bucket, req.folder)
    return CreateFolderResponse(bucket=req.bucket, folder=created)
