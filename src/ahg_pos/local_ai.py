"""Optional local language-model layer backed by Ollama.

The catalog recommender remains authoritative. Ollama can only improve the
conversation: questions, explanations and usage guidance. It never supplies
prices, stock or product ids to the client.
"""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .config import settings


class LocalAIUnavailable(RuntimeError):
    """Raised when the optional local model cannot be reached."""


def _candidate_context(candidates: list[dict[str, Any]]) -> str:
    rows = []
    for product in candidates[:5]:
        rows.append(
            {
                "id": str(product.get("id", "")),
                "name": product.get("name", ""),
                "category": product.get("category", ""),
                "technical_description": product.get("technical_description", ""),
                "price": product.get("price", 0),
                "stock": product.get("stock", 0),
                "tags": product.get("tags", ""),
            }
        )
    return json.dumps(rows, ensure_ascii=False)


def _prompt(query: str, history: list[dict[str, Any]], candidates: list[dict[str, Any]]) -> str:
    recent = [
        {"role": item.get("role", ""), "content": str(item.get("content", ""))[:500]}
        for item in history[-6:]
        if isinstance(item, dict)
    ]
    return f"""Eres el asesor técnico local de una ferretería dominicana.
Conversas en español claro y breve. Tu trabajo es descubrir la necesidad,
hacer preguntas de filtro y explicar productos que ya fueron encontrados por
el sistema. Nunca inventes productos, precios, stock, medidas ni compatibilidad.
No sustituyas a un técnico para electricidad, gas, estructura o riesgos.

Consulta actual: {query}
Historial: {json.dumps(recent, ensure_ascii=False)}
Candidatos reales disponibles en la BD: {_candidate_context(candidates)}

Reglas:
1. Si falta un dato crítico, pregunta antes de recomendar: material/tipo,
medida o diámetro, presentación/capacidad, uso y cantidad según corresponda.
2. Para tubos pregunta material, diámetro y si es agua fría o caliente.
3. Para pintura pregunta color, interior/exterior, tipo y presentación.
4. Para herramientas pregunta tipo de trabajo, medida y fuente de energía.
5. Solo menciona candidatos de la lista y no cambies sus nombres.
6. Devuelve únicamente JSON válido con este formato:
{{"reply":"...","next_questions":["..."],"selected_ids":["..."]}}

La respuesta debe ser útil para que el cliente elija y luego pueda crear una preorden."""


def _extract_json(raw: str) -> dict[str, Any] | None:
    raw = (raw or "").strip()
    raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.IGNORECASE)
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", raw, flags=re.DOTALL)
        if not match:
            return None
        try:
            value = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return value if isinstance(value, dict) else None


def consult_local_model(
    query: str,
    history: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Return safe conversational output, or None when Ollama is unavailable."""
    if not settings.ollama_enabled or not settings.ollama_model or not query.strip():
        return None
    payload = json.dumps(
        {
            "model": settings.ollama_model,
            "prompt": _prompt(query, history, candidates),
            "stream": False,
            "format": "json",
            "think": False,
            "options": {"temperature": 0.15, "num_ctx": 2048, "num_predict": 180},
        },
        ensure_ascii=False,
    ).encode("utf-8")
    request = Request(
        f"{settings.ollama_base_url}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=settings.ollama_timeout_seconds) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (OSError, HTTPError, URLError, TimeoutError, json.JSONDecodeError):
        raise LocalAIUnavailable("Ollama no esta disponible en este momento.")

    result = _extract_json(str(body.get("response", "")))
    if not result or not isinstance(result.get("reply"), str):
        raise LocalAIUnavailable("Ollama devolvio una respuesta no valida.")
    allowed_ids = {str(item.get("id")) for item in candidates}
    selected_ids = [str(item) for item in result.get("selected_ids", []) if str(item) in allowed_ids]
    questions = [str(item).strip() for item in result.get("next_questions", []) if str(item).strip()][:4]
    reply = result["reply"].strip()[:1200]
    for product in candidates:
        product_id = str(product.get("id", ""))
        if product_id:
            reply = reply.replace(product_id, str(product.get("name", "producto disponible")))
    return {
        "reply": reply,
        "next_questions": questions,
        "selected_ids": selected_ids,
        "model": settings.ollama_model,
    }
