from src.common.rabbitmq import consume_queue

QUEUE_NAME = "painel"
ROUTING_KEYS = ["excedente.iniciado", "excedente.terminado"]


def handle_excedente_painel(routing_key: str, payload: dict, _channel) -> None:
    periodo = payload.get("periodo")
    saldo_kw = payload.get("saldo_kw")
    if routing_key == "excedente.iniciado":
        print(
            f"[PAINEL] Período {periodo}: Estado atualizado -> EM EXCEDENTE ({saldo_kw:+.2f} kW).",
            flush=True,
        )
    elif routing_key == "excedente.terminado":
        print(
            f"[PAINEL] Período {periodo}: Estado atualizado -> SEM EXCEDENTE ({saldo_kw:+.2f} kW).",
            flush=True,
        )


def main() -> None:
    consume_queue(
        queue_name=QUEUE_NAME,
        routing_keys=ROUTING_KEYS,
        handler=handle_excedente_painel,
        prefetch_count=1,
    )


if __name__ == "__main__":
    main()
