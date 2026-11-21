import json
from fastapi import APIRouter
from pydantic import BaseModel, Field
from app.modules.runs.repository import lookup
from .repository import (save_comparison, list_comparisons, load, set_note)
from .service import compare_runs, comparison_id
from app.store import connection

router = APIRouter()


class CompareRequest(BaseModel):
    base_run_id: str = Field(min_length=1, max_length=128)
    target_run_id: str = Field(min_length=1, max_length=128)


class NoteRequest(BaseModel):
    note: str = Field(default='', max_length=500)


@router.post('/api/compare')
def create(request: CompareRequest):
    compare_id = comparison_id(request.base_run_id, request.target_run_id)
    with connection() as db:
        base = lookup(db, request.base_run_id)
        target = lookup(db, request.target_run_id)
        base_run, target_run = json.loads(base['result']), json.loads(target['result'])
    report = compare_runs(base_run, target_run)
    save_comparison(compare_id, request.base_run_id, request.target_run_id, report)
    return {'comparison_id': compare_id, **load(compare_id)}


@router.get('/api/compare')
def index():
    return list_comparisons()


@router.get('/api/compare/{compare_id}')
def detail(compare_id: str):
    return load(compare_id)


@router.post('/api/compare/{compare_id}/notes/{parcel_key}')
def annotate(compare_id: str, parcel_key: str, request: NoteRequest):
    return set_note(compare_id, parcel_key, request.note)
