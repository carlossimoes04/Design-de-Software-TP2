def classificar_sem_ia(
    producao_atual_kw: float,
    media_vizinhos_kw: float,
    historico_4_periodos: list[float],
) -> tuple[str, str]:
    """
    Regra determinística de fallback (sem IA), baseada apenas nos números de produção:
    1. Queda para perto de zero (<= 10% da média dos vizinhos) -> avaria
    2. Descida gradual nos últimos 4 períodos (> 10% da média dos vizinhos) -> sujidade
    3. Falta de histórico, queda súbita sem contexto claro ou qualquer dúvida -> avaria
    """
    if media_vizinhos_kw <= 0 or producao_atual_kw <= 0.10 * media_vizinhos_kw:
        return (
            "avaria",
            "Regra sem IA (fallback): produção caiu para perto de zero (<= 10% da média dos vizinhos).",
        )

    if len(historico_4_periodos) >= 4:
        ultimos_4 = historico_4_periodos[-4:]
        descida_gradual = (
            ultimos_4[0] > ultimos_4[1] > ultimos_4[2] > ultimos_4[3]
        )
        if descida_gradual:
            return (
                "sujidade",
                "Regra sem IA (fallback): descida gradual contínua nos últimos 4 períodos mantendo-se acima de 10% dos vizinhos.",
            )

    return (
        "avaria",
        "Regra sem IA (fallback): sem evidência clara de descida gradual ou histórico insuficiente; na dúvida assume-se avaria.",
    )
