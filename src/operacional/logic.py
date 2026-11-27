from collections import defaultdict
from typing import Callable

from src.operacional.db import OperationalDB

CAUSA_PARA_ACAO = {
    "sombra": "nenhuma",
    "sujidade": "avisar_limpeza",
    "avaria": "pedido_intervencao",
}


class OperationalService:
    def __init__(
        self,
        db: OperationalDB,
        publish_fn: Callable[[str, dict], None],
    ) -> None:
        self.db = db
        self.publish = publish_fn

    def handle_event(self, routing_key: str, payload: dict) -> None:
        if routing_key == "consumo.medido":
            self._handle_consumo_medido(payload)
        elif routing_key == "producao.medida":
            self._handle_producao_medida(payload)
        elif routing_key == "periodo.encerrado":
            self._handle_periodo_encerrado(payload)
        elif routing_key == "anomalia.classificada":
            self._handle_anomalia_classificada(payload)

    def _handle_consumo_medido(self, payload: dict) -> None:
        casa_id = str(payload["casa_id"])
        periodo = int(payload["periodo"])
        kw = float(payload["potencia_media_kw"])

        if self.db.periodo_esta_fechado(periodo):
            inserted = self.db.guardar_medicao_atrasada("consumo", casa_id, periodo, kw)
            if inserted:
                print(
                    f"[OPERACIONAL][AUDITORIA] Consumo atrasado guardado: casa={casa_id}, periodo={periodo}, kw={kw:.2f}",
                    flush=True,
                )
            return

        inserted = self.db.guardar_consumo(casa_id, periodo, kw)
        if not inserted:
            print(
                f"[OPERACIONAL][DUPLICADO] Consumo ignorado: casa={casa_id}, periodo={periodo}",
                flush=True,
            )

    def _handle_producao_medida(self, payload: dict) -> None:
        telhado_id = str(payload["telhado_id"])
        rua_id = str(payload["rua_id"])
        periodo = int(payload["periodo"])
        kw = float(payload["potencia_media_kw"])

        if self.db.periodo_esta_fechado(periodo):
            inserted = self.db.guardar_medicao_atrasada(
                "producao", telhado_id, periodo, kw, rua_id=rua_id
            )
            if inserted:
                print(
                    f"[OPERACIONAL][AUDITORIA] Produção atrasada guardada: telhado={telhado_id}, periodo={periodo}, kw={kw:.2f}",
                    flush=True,
                )
            return

        inserted = self.db.guardar_producao(telhado_id, rua_id, periodo, kw)
        if not inserted:
            print(
                f"[OPERACIONAL][DUPLICADO] Produção ignorada: telhado={telhado_id}, periodo={periodo}",
                flush=True,
            )

    def _handle_periodo_encerrado(self, payload: dict) -> None:
        periodo = int(payload["periodo"])
        if self.db.periodo_esta_fechado(periodo):
            return

        producao_total, consumo_total = self.db.obter_totais_periodo(periodo)
        producao_total = round(producao_total, 4)
        consumo_total = round(consumo_total, 4)
        saldo = round(producao_total - consumo_total, 4)
        estava_em_excedente = self.db.obter_em_excedente()
        agora_em_excedente = saldo > 0

        self.db.fechar_periodo(
            periodo=periodo,
            producao_total_kw=producao_total,
            consumo_total_kw=consumo_total,
            saldo_kw=saldo,
            novo_em_excedente=agora_em_excedente,
        )

        self.publish(
            "saldo.calculado",
            {
                "periodo": periodo,
                "producao_total_kw": producao_total,
                "consumo_total_kw": consumo_total,
                "saldo_kw": saldo,
            },
        )
        print(
            f"[OPERACIONAL][SALDO] Período {periodo}: producao={producao_total:.2f} kW, "
            f"consumo={consumo_total:.2f} kW, saldo={saldo:+.2f} kW",
            flush=True,
        )

        if agora_em_excedente and not estava_em_excedente:
            self.publish("excedente.iniciado", {"periodo": periodo, "saldo_kw": saldo})
        elif not agora_em_excedente and estava_em_excedente:
            self.publish("excedente.terminado", {"periodo": periodo, "saldo_kw": saldo})

        self._detetar_anomalias(periodo)

    def _detetar_anomalias(self, periodo: int) -> None:
        producoes = self.db.obter_producoes_periodo(periodo)
        por_rua: dict[str, list[dict]] = defaultdict(list)
        for registo in producoes:
            por_rua[registo["rua_id"]].append(registo)

        for rua_id, telhados in por_rua.items():
            for telhado in telhados:
                vizinhos = [t for t in telhados if t["telhado_id"] != telhado["telhado_id"]]
                if len(vizinhos) < 3:
                    continue

                media_vizinhos = sum(v["potencia_media_kw"] for v in vizinhos) / len(vizinhos)
                if media_vizinhos <= 0:
                    continue

                producao_kw = telhado["potencia_media_kw"]
                # 40% ou mais abaixo da média dos vizinhos
                if producao_kw <= (0.6 * media_vizinhos) + 1e-9:
                    evento = {
                        "telhado_id": telhado["telhado_id"],
                        "rua_id": rua_id,
                        "periodo": periodo,
                        "producao_kw": round(producao_kw, 4),
                        "media_vizinhos_kw": round(media_vizinhos, 4),
                        "num_vizinhos": len(vizinhos),
                    }
                    self.publish("producao.anomala", evento)
                    print(
                        f"[OPERACIONAL][DETECAO] Anomalia no telhado {telhado['telhado_id']} "
                        f"(rua {rua_id}, período {periodo}): {producao_kw:.2f} kW vs média vizinhos {media_vizinhos:.2f} kW",
                        flush=True,
                    )

    def _handle_anomalia_classificada(self, payload: dict) -> None:
        telhado_id = str(payload["telhado_id"])
        periodo = int(payload["periodo"])
        causa = str(payload["causa"])
        justificacao = str(payload.get("justificacao", ""))

        acao = CAUSA_PARA_ACAO.get(causa, "pedido_intervencao")
        inserted = self.db.registar_acao(telhado_id, periodo, causa, acao, justificacao)
        if not inserted:
            return

        if acao == "nenhuma":
            print(
                f"[OPERACIONAL][ACAO] Telhado {telhado_id} (período {periodo}) | causa=sombra -> Nenhuma ação. ({justificacao})",
                flush=True,
            )
        elif acao == "avisar_limpeza":
            print(
                f"[OPERACIONAL][AVISO LIMPEZA] Telhado {telhado_id} (período {periodo}): "
                f"avisar membro para limpar o painel. ({justificacao})",
                flush=True,
            )
        else:
            print(
                f"[OPERACIONAL][PEDIDO INTERVENCAO] Telhado {telhado_id} (período {periodo}): "
                f"registado pedido de intervenção para técnicos externos. ({justificacao})",
                flush=True,
            )
