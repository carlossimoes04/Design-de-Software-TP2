import os

from src.common.rabbitmq import consume_queue, publish_event
from src.operacional.db import OperationalDB
from src.operacional.logic import OperationalService

QUEUE_NAME = "operacional"
ROUTING_KEYS = [
    "consumo.medido",
    "producao.medida",
    "periodo.encerrado",
    "anomalia.classificada",
]


def main() -> None:
    db_path = os.environ.get("DB_PATH", "operacional.db")
    db = OperationalDB(db_path=db_path)

    def _handler(routing_key: str, payload: dict, channel) -> None:
        service = OperationalService(
            db=db,
            publish_fn=lambda rk, data: publish_event(channel, rk, data),
        )
        service.handle_event(routing_key, payload)

    try:
        consume_queue(queue_name=QUEUE_NAME, routing_keys=ROUTING_KEYS, handler=_handler, prefetch_count=1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
