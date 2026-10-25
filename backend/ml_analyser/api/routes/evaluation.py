"""Public, bounded prediction comparison. Uploaded data is not persisted or sent to a model."""

from threading import BoundedSemaphore

from fastapi import APIRouter, HTTPException

from ml_analyser.evaluation.predictions import (
    PredictionReport,
    PredictionRequest,
    compare_predictions,
)

router = APIRouter(prefix="/evaluation", tags=["prediction comparison"])
comparison_slot = BoundedSemaphore(1)


@router.post("/compare", response_model=PredictionReport)
def compare(request: PredictionRequest) -> PredictionReport:
    if not comparison_slot.acquire(blocking=False):
        raise HTTPException(429, "Another comparison is running. Please retry shortly.")
    try:
        return compare_predictions(request)
    except (ValueError, OverflowError) as error:
        raise HTTPException(422, str(error)) from error
    finally:
        comparison_slot.release()
