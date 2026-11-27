import os

from src.common.rabbitmq import consume_queue, publish_event
from src.triagem.db import TriageDB
from src.triagem.logic import TriageService
from src.triagem.model import FakeTriageModel, OllamaTriageModel, TriageModel

QUEUE_NAME = "triagem"
ROUTING_KEYS = [
    "producao.medida",
    "relato.recebido",
    "producao.anomala",
]


def create_model() -> TriageModel:
    mode = os.environ.get("TRIAGE_MODE", "ollama").strip().lower()
    if mode == "fake":
        print("[TRIAGEM] A usar FakeTriageModel.", flush=True)
        return FakeTriageModel()
    model = OllamaTriageModel()
    print(f"[TRIAGEM] A usar OllamaTriageModel ({model.model} em {model.base_url}).", flush=True)
    return model


def main() -> None:
    db_path = os.environ.get("DB_PATH", "triagem.db")
    db = TriageDB(db_path=db_path)
    model = create_model()

    def _handler(routing_key: str, payload: dict, channel) -> None:
        service = TriageService(
            db=db,
            model=model,
            publish_fn=lambda rk, data: publish_event(channel, rk, data),
        )
        service.handle_event(routing_key, payload)

    try:
        # prefetch_count=1 garante processamento de uma anomalia de cada vez
        consume_queue(
            queue_name=QUEUE_NAME,
            routing_keys=ROUTING_KEYS,
            handler=_handler,
            prefetch_count=1,
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()
