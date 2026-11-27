import argparse
import json
import os
from pathlib import Path

from src.triagem.db import TriageDB
from src.triagem.logic import TriageService
from src.triagem.model import FakeTriageModel, OllamaTriageModel, TriageModel

DEFAULT_SCENARIOS = Path(__file__).parent / "cenarios.json"


def run_evals(model: TriageModel, scenarios_path: Path = DEFAULT_SCENARIOS) -> list[dict]:
    cenarios = json.loads(scenarios_path.read_text(encoding="utf-8"))
    resultados: list[dict] = []

    for cenario in cenarios:
        db = TriageDB(":memory:")
        publicados: list[tuple[str, dict]] = []
        service = TriageService(
            db=db,
            model=model,
            publish_fn=lambda rk, data: publicados.append((rk, data)),
        )

        telhado_id = cenario["telhado_id"]
        rua_id = cenario["rua_id"]
        periodo = int(cenario["periodo"])
        historico = cenario["historico_4_periodos"]

        # Alimentar vista local CQRS pelos eventos (4 períodos do telhado + vizinhos + relatos)
        inicio_periodo = periodo - len(historico) + 1
        for offset, kw in enumerate(historico):
            service.handle_event(
                "producao.medida",
                {
                    "telhado_id": telhado_id,
                    "rua_id": rua_id,
                    "periodo": inicio_periodo + offset,
                    "potencia_media_kw": float(kw),
                },
            )

        vizinhos = cenario["vizinhos"]
        for v in vizinhos:
            service.handle_event(
                "producao.medida",
                {
                    "telhado_id": v["telhado_id"],
                    "rua_id": rua_id,
                    "periodo": periodo,
                    "potencia_media_kw": float(v["potencia_media_kw"]),
                },
            )

        for idx, texto in enumerate(cenario.get("relatos", []), start=1):
            service.handle_event(
                "relato.recebido",
                {
                    "relato_id": f"{cenario['id']}_R{idx}",
                    "telhado_id": telhado_id,
                    "periodo": periodo,
                    "texto": texto,
                },
            )

        media_vizinhos = sum(float(v["potencia_media_kw"]) for v in vizinhos) / len(vizinhos)
        service.handle_event(
            "producao.anomala",
            {
                "telhado_id": telhado_id,
                "rua_id": rua_id,
                "periodo": periodo,
                "producao_kw": float(historico[-1]),
                "media_vizinhos_kw": round(media_vizinhos, 4),
                "num_vizinhos": len(vizinhos),
            },
        )

        registos = db.listar_registos()
        registo = registos[0] if registos else {}
        evento_pub = publicados[0][1] if publicados else {}
        causa_obtida = evento_pub.get("causa")
        esperada = cenario["causa_esperada"]

        resultados.append(
            {
                "id": cenario["id"],
                "causa_esperada": esperada,
                "causa_obtida": causa_obtida,
                "acertou": causa_obtida == esperada,
                "origem": registo.get("origem"),
                "resposta_bruta": registo.get("resposta_bruta"),
                "justificacao": evento_pub.get("justificacao"),
            }
        )
        db.close()

    return resultados


def main() -> None:
    parser = argparse.ArgumentParser(description="Executa os evals de triagem do Bairro Solar.")
    parser.add_argument(
        "--real",
        action="store_true",
        help="Usa o modelo real (Ollama, temperatura 0) em vez do FakeTriageModel.",
    )
    parser.add_argument(
        "--ollama-url",
        default=os.environ.get("OLLAMA_URL", "http://localhost:11434"),
        help="URL do Ollama quando --real está ativo.",
    )
    parser.add_argument(
        "--model",
        default=os.environ.get("OLLAMA_MODEL", "gemma4:e4b"),
        help="Nome do modelo no Ollama quando --real está ativo.",
    )
    args = parser.parse_args()

    if args.real:
        model: TriageModel = OllamaTriageModel(base_url=args.ollama_url, model=args.model)
        print(f"A correr evals com modelo REAL ({args.model} em {args.ollama_url}, temperature=0)...")
    else:
        model = FakeTriageModel()
        print("A correr evals com FakeTriageModel...")

    resultados = run_evals(model=model)
    acertos = sum(1 for r in resultados if r["acertou"])

    for r in resultados:
        estado = "OK" if r["acertou"] else "FALHOU"
        print(
            f"[{estado}] {r['id']}: esperada={r['causa_esperada']} | "
            f"obtida={r['causa_obtida']} (origem={r['origem']})"
        )
        if not r["acertou"]:
            print(f"    resposta_bruta={r['resposta_bruta']}")

    print(f"\nResultado final: {acertos}/{len(resultados)} causas certas.")


if __name__ == "__main__":
    main()
