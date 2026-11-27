from src.common.rabbitmq import consume_queue

QUEUE_NAME = "aviso"
ROUTING_KEYS = ["excedente.iniciado", "excedente.terminado"]


def handle_excedente_aviso(routing_key: str, payload: dict, _channel) -> None:
    periodo = payload.get("periodo")
    saldo_kw = payload.get("saldo_kw")
    if routing_key == "excedente.iniciado":
        print(
            f"[AVISO] Período {periodo}: EXCEDENTE INICIADO (saldo {saldo_kw:+.2f} kW) — membros avisados para aproveitar energia renovável.",
            flush=True,
        )
    elif routing_key == "excedente.terminado":
        print(
            f"[AVISO] Período {periodo}: EXCEDENTE TERMINADO (saldo {saldo_kw:+.2f} kW) — membros avisados do fim do excedente.",
            flush=True,
        )


def main() -> None:
    consume_queue(
        queue_name=QUEUE_NAME,
        routing_keys=ROUTING_KEYS,
        handler=handle_excedente_aviso,
        prefetch_count=1,
    )


if __name__ == "__main__":
    main()
