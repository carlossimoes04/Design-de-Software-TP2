import json
import os
import re
from abc import ABC, abstractmethod

import requests

VALID_CAUSAS = {"sombra", "sujidade", "avaria"}


def validate_model_response(raw_text: str) -> tuple[str, str] | None:
    """Valida a resposta contra {"causa": "sombra"|"sujidade"|"avaria", "justificacao": "..."}."""
    if not raw_text or not isinstance(raw_text, str):
        return None
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return None

    if not isinstance(data, dict):
        return None

    causa = data.get("causa")
    justificacao = data.get("justificacao")
    if causa not in VALID_CAUSAS:
        return None
    if not isinstance(justificacao, str) or not justificacao.strip():
        return None
    return causa, justificacao.strip()


class TriageModel(ABC):
    @abstractmethod
    def classify(self, system_prompt: str, user_prompt: str) -> str:
        """Recebe system_prompt e user_prompt e devolve a resposta bruta do modelo."""


class OllamaTriageModel(TriageModel):
    def __init__(
        self,
        base_url: str | None = None,
        model: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self.base_url = (base_url or os.environ.get("OLLAMA_URL", "http://host.docker.internal:11434")).rstrip("/")
        self.model = model or os.environ.get("OLLAMA_MODEL", "gemma4:e4b")
        self.timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else float(os.environ.get("OLLAMA_TIMEOUT", "120"))
        )

    def classify(self, system_prompt: str, user_prompt: str) -> str:
        response = requests.post(
            f"{self.base_url}/api/chat",
            json={
                "model": self.model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "stream": False,
                "format": "json",
                "think": False,
                "options": {"temperature": 0},
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        payload = response.json()
        return str(payload.get("message", {}).get("content", ""))


class FakeTriageModel(TriageModel):
    """
    Modelo determinístico para testes e evals sem chamar a API real.
    Pode ser configurado para devolver uma resposta fixa ou lançar erro (para testar fallback).
    """

    def __init__(
        self,
        fixed_response: str | None = None,
        raise_error: Exception | None = None,
    ) -> None:
        self.fixed_response = fixed_response
        self.raise_error = raise_error

    def classify(self, system_prompt: str, user_prompt: str) -> str:
        if self.raise_error is not None:
            raise self.raise_error
        if self.fixed_response is not None:
            return self.fixed_response

        # Extrair números do histórico e média dos vizinhos
        hist_match = re.search(r"Histórico últimos 4 períodos \(kW\): \[(.*?)\]", user_prompt)
        media_match = re.search(r"Média simples dos vizinhos \(kW\): ([0-9.]+)", user_prompt)
        relatos_match = re.search(
            r"<relatos_morador>(.*?)</relatos_morador>", user_prompt, flags=re.DOTALL
        )

        historico = []
        if hist_match and hist_match.group(1).strip():
            historico = [float(x.strip()) for x in hist_match.group(1).split(",") if x.strip()]
        media_vizinhos = float(media_match.group(1)) if media_match else 0.0
        relatos_txt = (relatos_match.group(1).lower() if relatos_match else "").strip()

        # Ignorar frases típicas de prompt injection dentro dos relatos
        relatos_limpos = re.sub(
            r"(ignora\s+tudo|ignore\s+all|esquece\s+as\s+instru[cç][oõ]es|regista\s+uma\s+avaria|responde\s+avaria)",
            "",
            relatos_txt,
        )

        producao_atual = historico[-1] if historico else 0.0

        # 1. Queda para perto de zero sem evidência de sombra/sujidade -> avaria
        if media_vizinhos > 0 and producao_atual <= 0.10 * media_vizinhos:
            return json.dumps(
                {
                    "causa": "avaria",
                    "justificacao": "Queda abrupta da produção para perto de zero face aos vizinhos.",
                },
                ensure_ascii=False,
            )

        # 2. Pistas de sombra temporária (andaime, grua, toldo, obras, sombra)
        if any(k in relatos_limpos for k in ("andaime", "grua", "toldo", "obras", "sombra")):
            return json.dumps(
                {
                    "causa": "sombra",
                    "justificacao": "Queda parcial compatível com sombra temporária indicada no relato.",
                },
                ensure_ascii=False,
            )

        # 3. Pistas de sujidade (folhas, pó, poeira, sujo, sujidade, limpar) ou descida gradual
        descida_gradual = (
            len(historico) >= 4
            and historico[-4] > historico[-3] > historico[-2] > historico[-1]
        )
        if descida_gradual or any(
            k in relatos_limpos for k in ("folha", "pó", "poeira", "suj", "limpar")
        ):
            return json.dumps(
                {
                    "causa": "sujidade",
                    "justificacao": "Descida gradual/relato compatível com acumulação de sujidade no painel.",
                },
                ensure_ascii=False,
            )

        return json.dumps(
            {
                "causa": "avaria",
                "justificacao": "Sem contexto compatível com sombra ou sujidade; classificado como avaria.",
            },
            ensure_ascii=False,
        )
