from sqlalchemy.orm import Session

from app.testing.load_simulator import simulate_burst


def simulate_queue_saturation(db: Session, session_id: str, count: int = 25) -> dict:
    prompts = [
        f"stress workload {index}: validate queue saturation and scheduling stability"
        for index in range(count)
    ]
    return simulate_burst(db=db, session_id=session_id, prompts=prompts, wait_for_results=False)

