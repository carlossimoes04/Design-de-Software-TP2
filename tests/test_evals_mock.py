from evals.run_evals import run_evals
from src.triagem.model import FakeTriageModel


def test_evals_com_modelo_falso():
    resultados = run_evals(model=FakeTriageModel())
    assert len(resultados) >= 4
    for r in resultados:
        assert r["origem"] == "ia", f"Cenário {r['id']} caiu em fallback inesperadamente"
        assert r["acertou"], f"Cenário {r['id']} falhou: esperada={r['causa_esperada']}, obtida={r['causa_obtida']}"
