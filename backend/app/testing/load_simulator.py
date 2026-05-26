from concurrent.futures import Future

from sqlalchemy.orm import Session

from app.orchestration.queue_manager import queue_manager
from app.orchestration.scheduler import assign_priority
from app.services.request_service import create_queued_request


def simulate_burst(
    db: Session,
    session_id: str,
    prompts: list[str],
    wait_for_results: bool = False,
) -> dict:
    futures: list[Future] = []
    request_ids: list[int] = []
    for prompt in prompts:
        priority = assign_priority(prompt)
        request = create_queued_request(db, session_id=session_id, prompt=prompt, priority=priority)
        request_ids.append(request.id)
        futures.append(
            queue_manager.enqueue(
                request_id=request.id,
                prompt=prompt,
                priority=priority,
                memory_context=[],
            )
        )

    completed = 0
    failed = 0
    if wait_for_results:
        for future in futures:
            try:
                future.result(timeout=30)
                completed += 1
            except Exception:
                failed += 1

    return {
        "submitted": len(prompts),
        "request_ids": request_ids,
        "completed": completed,
        "failed": failed,
        "queue": queue_manager.snapshot(),
    }

