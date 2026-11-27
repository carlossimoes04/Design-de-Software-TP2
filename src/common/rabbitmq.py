import json
import os
import time
from typing import Callable, Iterable

import pika

EXCHANGE_NAME = "bairro_solar"
EXCHANGE_TYPE = "topic"


def get_rabbitmq_host() -> str:
    return os.environ.get("RABBITMQ_HOST", "broker")


def connect_with_retry(
    host: str | None = None,
    max_retries: int = 30,
    delay_seconds: float = 2.0,
) -> pika.BlockingConnection:
    target_host = host or get_rabbitmq_host()
    params = pika.ConnectionParameters(
        host=target_host,
        heartbeat=60,
        blocked_connection_timeout=30,
    )
    last_error: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            conn = pika.BlockingConnection(params)
            print(f"[rabbitmq] Ligado ao broker '{target_host}' (tentativa {attempt}).", flush=True)
            return conn
        except Exception as exc:
            last_error = exc
            print(
                f"[rabbitmq] Broker '{target_host}' indisponível (tentativa {attempt}/{max_retries}): {exc}",
                flush=True,
            )
            time.sleep(delay_seconds)
    raise RuntimeError(f"Não foi possível ligar ao RabbitMQ em '{target_host}': {last_error}")


def setup_channel(connection: pika.BlockingConnection) -> pika.adapters.blocking_connection.BlockingChannel:
    channel = connection.channel()
    channel.exchange_declare(
        exchange=EXCHANGE_NAME,
        exchange_type=EXCHANGE_TYPE,
        durable=True,
    )
    channel.confirm_delivery()
    return channel


def publish_event(
    channel: pika.adapters.blocking_connection.BlockingChannel,
    routing_key: str,
    payload: dict,
) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    channel.basic_publish(
        exchange=EXCHANGE_NAME,
        routing_key=routing_key,
        body=body,
        properties=pika.BasicProperties(
            delivery_mode=2,  # persistent
            content_type="application/json",
        ),
    )


def consume_queue(
    queue_name: str,
    routing_keys: Iterable[str],
    handler: Callable[[str, dict, pika.adapters.blocking_connection.BlockingChannel], None],
    prefetch_count: int = 1,
    host: str | None = None,
) -> None:
    connection = connect_with_retry(host=host)
    channel = setup_channel(connection)
    channel.queue_declare(queue=queue_name, durable=True)
    for key in routing_keys:
        channel.queue_bind(exchange=EXCHANGE_NAME, queue=queue_name, routing_key=key)
    channel.basic_qos(prefetch_count=prefetch_count)

    def _on_message(ch, method, properties, body):
        try:
            payload = json.loads(body.decode("utf-8"))
        except Exception as exc:
            print(f"[{queue_name}] Mensagem inválida em {method.routing_key}: {exc}", flush=True)
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=False)
            return

        try:
            handler(method.routing_key, payload, ch)
            ch.basic_ack(delivery_tag=method.delivery_tag)
        except Exception as exc:
            print(f"[{queue_name}] Erro ao processar {method.routing_key}: {exc}", flush=True)
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)

    channel.basic_consume(
        queue=queue_name,
        on_message_callback=_on_message,
        auto_ack=False,
    )
    print(f"[{queue_name}] A consumir fila '{queue_name}' (chaves: {list(routing_keys)})...", flush=True)
    try:
        channel.start_consuming()
    except KeyboardInterrupt:
        channel.stop_consuming()
    finally:
        if connection.is_open:
            connection.close()
