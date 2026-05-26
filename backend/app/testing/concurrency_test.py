from concurrent.futures import ThreadPoolExecutor, as_completed

from app.database.session import SessionLocal
from app.testing.load_simulator import simulate_burst


def simulate_high_concurrency(session_id: str, workers: int = 4, per_worker: int = 5) -> dict:
    prompts_by_worker = [
        [
            f"concurrency worker {worker} request {index}: operational reliability check"
            for index in range(per_worker)
        ]
        for worker in range(workers)
    ]

    def submit_worker(prompts: list[str]) -> dict:
        db = SessionLocal()
        try:
            return simulate_burst(db, session_id, prompts, False)
        finally:
            db.close()

    submitted = 0
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [
            executor.submit(submit_worker, prompts)
            for prompts in prompts_by_worker
        ]
        for future in as_completed(futures):
            submitted += future.result()["submitted"]
    return {"workers": workers, "submitted": submitted}
