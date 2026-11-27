from src.triagem.db import TriageDB
from src.triagem.model import FakeTriageModel, validate_model_response
from src.triagem.logic import TriageService


def test_validacao_json_estrita():
    assert validate_model_response('{"causa": "sombra", "justificacao": "andaime"}') == ("sombra", "andaime")
    assert validate_model_response('{"causa": "inventada", "justificacao": "x"}') is None
    assert validate_model_response('{"causa": "avaria", "justificacao": ""}') is None
    assert validate_model_response("texto livre fora de json") is None


def test_f4_modelo_em_baixo_usa_regra_sem_ia_avaria_e_sujidade():
    db = TriageDB(":memory:")
    published: list[tuple[str, dict]] = []
    broken_model = FakeTriageModel(raise_error=ConnectionError("Ollama em baixo"))
    service = TriageService(db=db, model=broken_model, publish_fn=lambda rk, d: published.append((rk, d)))

    # Caso 1: queda para perto de zero -> avaria via fallback
    for p, kw in [(1, 4.0), (2, 4.0), (3, 4.0), (4, 0.1)]:
        service.handle_event("producao.medida", {"telhado_id": "T09", "rua_id": "rua_3", "periodo": p, "potencia_media_kw": kw})
    service.handle_event(
        "producao.anomala",
        {"telhado_id": "T09", "rua_id": "rua_3", "periodo": 4, "producao_kw": 0.1, "media_vizinhos_kw": 4.0, "num_vizinhos": 3},
    )

    # Caso 2: descida gradual mantendo-se > 10% -> sujidade via fallback
    for p, kw in [(1, 4.0), (2, 3.3), (3, 2.6), (4, 1.9)]:
        service.handle_event("producao.medida", {"telhado_id": "T05", "rua_id": "rua_2", "periodo": p, "potencia_media_kw": kw})
    service.handle_event(
        "producao.anomala",
        {"telhado_id": "T05", "rua_id": "rua_2", "periodo": 4, "producao_kw": 1.9, "media_vizinhos_kw": 4.0, "num_vizinhos": 3},
    )

    # Caso 3: resposta inválida (não JSON) com queda súbita parcial (dúvida) -> avaria via fallback
    service.model = FakeTriageModel(fixed_response="nao sou json")
    for p, kw in [(1, 4.0), (2, 4.0), (3, 2.0), (4, 2.0)]:
        service.handle_event("producao.medida", {"telhado_id": "T01", "rua_id": "rua_1", "periodo": p, "potencia_media_kw": kw})
    service.handle_event(
        "producao.anomala",
        {"telhado_id": "T01", "rua_id": "rua_1", "periodo": 4, "producao_kw": 2.0, "media_vizinhos_kw": 4.0, "num_vizinhos": 3},
    )

    causas = {p["telhado_id"]: p["causa"] for _, p in published}
    assert causas == {"T09": "avaria", "T05": "sujidade", "T01": "avaria"}

    registos = db.listar_registos()
    assert len(registos) == 3
    assert all(r["origem"] == "fallback" for r in registos)
    db.close()


def test_triagem_idempotencia_redelivery():
    db = TriageDB(":memory:")
    published: list[tuple[str, dict]] = []
    service = TriageService(db=db, model=FakeTriageModel(), publish_fn=lambda rk, d: published.append((rk, d)))

    evento = {
        "telhado_id": "T09",
        "rua_id": "rua_3",
        "periodo": 4,
        "producao_kw": 0.1,
        "media_vizinhos_kw": 4.0,
        "num_vizinhos": 3,
    }
    service.handle_event("producao.anomala", evento)
    service.handle_event("producao.anomala", evento)

    assert len(published) == 1
    db.close()
