import argparse
import json
from pathlib import Path

from src.common.rabbitmq import connect_with_retry, publish_event, setup_channel

DEFAULT_SCENARIO = Path(__file__).parent / "cenarios" / "bairro_base.json"


def run_scenario(scenario_path: Path, host: str | None = None) -> None:
    data = json.loads(scenario_path.read_text(encoding="utf-8"))
    print(f"[SIMULADOR] A carregar cenário '{data.get('nome', scenario_path.name)}'...", flush=True)

    connection = connect_with_retry(host=host)
    channel = setup_channel(connection)

    try:
        for bloco in data["periodos"]:
            periodo = int(bloco["periodo"])
            print(f"[SIMULADOR] --- Período {periodo} ---", flush=True)

            # 1. Publicar relatos do período (antes de fechar para estarem na vista local da Triagem)
            for relato in bloco.get("relatos", []):
                publish_event(
                    channel,
                    "relato.recebido",
                    {
                        "relato_id": relato["relato_id"],
                        "telhado_id": relato["telhado_id"],
                        "periodo": periodo,
                        "texto": relato["texto"],
                    },
                )

            # 2. Publicar consumos (com suporte a duplicados simulando reenvio de gateway)
            for consumo in bloco.get("consumos", []):
                repeticoes = int(consumo.get("duplicar", 1))
                evento = {
                    "casa_id": consumo["casa_id"],
                    "periodo": periodo,
                    "potencia_media_kw": float(consumo["potencia_media_kw"]),
                }
                for _ in range(repeticoes):
                    publish_event(channel, "consumo.medido", evento)

            # 3. Publicar produções (com suporte a duplicados simulando reenvio de gateway)
            for prod in bloco.get("producoes", []):
                repeticoes = int(prod.get("duplicar", 1))
                evento = {
                    "telhado_id": prod["telhado_id"],
                    "rua_id": prod["rua_id"],
                    "periodo": periodo,
                    "potencia_media_kw": float(prod["potencia_media_kw"]),
                }
                for _ in range(repeticoes):
                    publish_event(channel, "producao.medida", evento)

            # 4. Encerrar período (sem esperas entre períodos)
            publish_event(channel, "periodo.encerrado", {"periodo": periodo})

            # 5. Publicar medições atrasadas (chegam depois de periodo.encerrado)
            for atrasado in bloco.get("atrasados_apos_fecho", []):
                tipo = atrasado["tipo"]
                if tipo == "consumo":
                    publish_event(
                        channel,
                        "consumo.medido",
                        {
                            "casa_id": atrasado["casa_id"],
                            "periodo": int(atrasado.get("periodo", periodo)),
                            "potencia_media_kw": float(atrasado["potencia_media_kw"]),
                        },
                    )
                elif tipo == "producao":
                    publish_event(
                        channel,
                        "producao.medida",
                        {
                            "telhado_id": atrasado["telhado_id"],
                            "rua_id": atrasado["rua_id"],
                            "periodo": int(atrasado.get("periodo", periodo)),
                            "potencia_media_kw": float(atrasado["potencia_media_kw"]),
                        },
                    )

        print("[SIMULADOR] Cenário concluído.", flush=True)
    finally:
        if connection.is_open:
            connection.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulador de eventos do Bairro Solar.")
    parser.add_argument(
        "cenario",
        nargs="?",
        default=str(DEFAULT_SCENARIO),
        help="Caminho para o ficheiro JSON do cenário.",
    )
    parser.add_argument(
        "--host",
        default=None,
        help="Host do RabbitMQ (por defeito usa RABBITMQ_HOST ou 'broker').",
    )
    args = parser.parse_args()
    run_scenario(Path(args.cenario), host=args.host)


if __name__ == "__main__":
    main()
