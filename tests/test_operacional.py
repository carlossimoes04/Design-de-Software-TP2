from src.operacional.db import OperationalDB
from src.operacional.logic import OperationalService


def _make_service():
    db = OperationalDB(":memory:")
    published: list[tuple[str, dict]] = []
    service = OperationalService(db=db, publish_fn=lambda rk, data: published.append((rk, data)))
    return db, service, published


def test_f1_duplicados_gateway_e_redelivery_contam_uma_vez():
    db, service, published = _make_service()

    # Mesmo valor (casa C01, período 1) entregue duas vezes (ex.: reenvio do gateway ou redelivery RabbitMQ)
    service.handle_event("consumo.medido", {"casa_id": "C01", "periodo": 1, "potencia_media_kw": 3.0})
    service.handle_event("consumo.medido", {"casa_id": "C01", "periodo": 1, "potencia_media_kw": 3.0})

    # Mesmo telhado (T01, período 1) entregue duas vezes
    service.handle_event(
        "producao.medida",
        {"telhado_id": "T01", "rua_id": "rua_1", "periodo": 1, "potencia_media_kw": 5.0},
    )
    service.handle_event(
        "producao.medida",
        {"telhado_id": "T01", "rua_id": "rua_1", "periodo": 1, "potencia_media_kw": 5.0},
    )

    # Encerrar período (inclusive testando redelivery de periodo.encerrado)
    service.handle_event("periodo.encerrado", {"periodo": 1})
    service.handle_event("periodo.encerrado", {"periodo": 1})

    saldos = [p for rk, p in published if rk == "saldo.calculado"]
    assert len(saldos) == 1
    assert saldos[0]["producao_total_kw"] == 5.0
    assert saldos[0]["consumo_total_kw"] == 3.0
    assert saldos[0]["saldo_kw"] == 2.0
    db.close()


def test_f1_valores_atrasados_guardados_auditoria_sem_alterar_saldo():
    db, service, published = _make_service()

    service.handle_event("consumo.medido", {"casa_id": "C01", "periodo": 1, "potencia_media_kw": 2.0})
    service.handle_event(
        "producao.medida",
        {"telhado_id": "T01", "rua_id": "rua_1", "periodo": 1, "potencia_media_kw": 4.0},
    )
    service.handle_event("periodo.encerrado", {"periodo": 1})

    # Medição atrasada chega depois de periodo.encerrado
    service.handle_event("consumo.medido", {"casa_id": "C02", "periodo": 1, "potencia_media_kw": 10.0})

    saldo_publicado = db.obter_saldo_publicado(1)
    assert saldo_publicado["saldo_kw"] == 2.0

    atrasados = db.listar_atrasados()
    assert len(atrasados) == 1
    assert atrasados[0]["origem_id"] == "C02"
    assert atrasados[0]["potencia_media_kw"] == 10.0
    db.close()


def test_f2_excedente_publicado_apenas_na_mudanca_de_estado():
    db, service, published = _make_service()

    # Período 1: saldo negativo -> sem evento de excedente
    service.handle_event("consumo.medido", {"casa_id": "C01", "periodo": 1, "potencia_media_kw": 5.0})
    service.handle_event("producao.medida", {"telhado_id": "T01", "rua_id": "rua_1", "periodo": 1, "potencia_media_kw": 2.0})
    service.handle_event("periodo.encerrado", {"periodo": 1})

    # Período 2: saldo positivo -> excedente.iniciado
    service.handle_event("consumo.medido", {"casa_id": "C01", "periodo": 2, "potencia_media_kw": 2.0})
    service.handle_event("producao.medida", {"telhado_id": "T01", "rua_id": "rua_1", "periodo": 2, "potencia_media_kw": 6.0})
    service.handle_event("periodo.encerrado", {"periodo": 2})

    # Período 3: continua positivo -> NÃO repete excedente.iniciado
    service.handle_event("consumo.medido", {"casa_id": "C01", "periodo": 3, "potencia_media_kw": 2.0})
    service.handle_event("producao.medida", {"telhado_id": "T01", "rua_id": "rua_1", "periodo": 3, "potencia_media_kw": 5.0})
    service.handle_event("periodo.encerrado", {"periodo": 3})

    # Período 4: volta a negativo -> excedente.terminado
    service.handle_event("consumo.medido", {"casa_id": "C01", "periodo": 4, "potencia_media_kw": 6.0})
    service.handle_event("producao.medida", {"telhado_id": "T01", "rua_id": "rua_1", "periodo": 4, "potencia_media_kw": 2.0})
    service.handle_event("periodo.encerrado", {"periodo": 4})

    eventos_excedente = [(rk, p["periodo"]) for rk, p in published if rk.startswith("excedente.")]
    assert eventos_excedente == [
        ("excedente.iniciado", 2),
        ("excedente.terminado", 4),
    ]
    db.close()


def test_detecao_anomalias_regras_vizinhos_e_rua_inteira():
    db, service, published = _make_service()

    # rua_1: T01 produz 2.0 vs 3 vizinhos a 4.0 (50% abaixo >= 40%) -> anomalia em T01
    for tid, kw in [("T01", 2.0), ("T02", 4.0), ("T03", 4.0), ("T04", 4.0)]:
        service.handle_event("producao.medida", {"telhado_id": tid, "rua_id": "rua_1", "periodo": 1, "potencia_media_kw": kw})

    # rua_2: só 2 vizinhos (3 telhados no total) -> não deteta anomalia
    for tid, kw in [("T05", 0.5), ("T06", 4.0), ("T07", 4.0)]:
        service.handle_event("producao.medida", {"telhado_id": tid, "rua_id": "rua_2", "periodo": 1, "potencia_media_kw": kw})

    # rua_3: rua inteira baixa para 1.0 -> sem anomalia
    for tid, kw in [("T09", 1.0), ("T10", 1.0), ("T11", 1.0), ("T12", 1.0)]:
        service.handle_event("producao.medida", {"telhado_id": tid, "rua_id": "rua_3", "periodo": 1, "potencia_media_kw": kw})

    service.handle_event("periodo.encerrado", {"periodo": 1})

    anomalias = [p for rk, p in published if rk == "producao.anomala"]
    assert len(anomalias) == 1
    assert anomalias[0]["telhado_id"] == "T01"
    assert anomalias[0]["num_vizinhos"] == 3
    db.close()


def test_acoes_por_causa_e_idempotencia():
    db, service, _ = _make_service()

    service.handle_event("anomalia.classificada", {"telhado_id": "T01", "periodo": 4, "causa": "sombra", "justificacao": "andaime"})
    service.handle_event("anomalia.classificada", {"telhado_id": "T05", "periodo": 4, "causa": "sujidade", "justificacao": "folhas"})
    service.handle_event("anomalia.classificada", {"telhado_id": "T09", "periodo": 4, "causa": "avaria", "justificacao": "zero"})
    # Duplicado ignorado
    service.handle_event("anomalia.classificada", {"telhado_id": "T09", "periodo": 4, "causa": "avaria", "justificacao": "zero"})

    acoes = {(a["telhado_id"], a["acao"]) for a in db.listar_acoes()}
    assert acoes == {
        ("T01", "nenhuma"),
        ("T05", "avisar_limpeza"),
        ("T09", "pedido_intervencao"),
    }
    db.close()
