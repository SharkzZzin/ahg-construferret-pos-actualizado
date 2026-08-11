from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

try:
    from .database import Database
    from .recommender import recommend_products
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from ahg_pos.database import Database
    from ahg_pos.recommender import recommend_products


DB = Database().connect()


TOOLS = [
    {
        "name": "buscar_articulos",
        "description": "Busca articulos de AHG CONSTRUFERRET por lenguaje natural y solo devuelve productos con existencia.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Necesidad o problema del cliente."},
                "limit": {"type": "integer", "default": 6},
            },
            "required": ["query"],
        },
    },
    {
        "name": "recomendar_articulos",
        "description": "Recomienda articulos tecnicos para resolver una necesidad y explica por que aplican.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "necesidad": {"type": "string", "description": "Descripcion natural del problema."},
                "presupuesto": {"type": "number", "description": "Presupuesto maximo opcional por articulo."},
                "limit": {"type": "integer", "default": 6},
            },
            "required": ["necesidad"],
        },
    },
    {
        "name": "stock_critico",
        "description": "Lista productos cuyo inventario esta en nivel critico.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def main() -> None:
    for line in sys.stdin:
        if not line.strip():
            continue
        try:
            request = json.loads(line)
            response = handle_request(request)
        except Exception as exc:
            response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32603, "message": str(exc)},
            }
        sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
        sys.stdout.flush()


def handle_request(request: dict[str, Any]) -> dict[str, Any]:
    method = request.get("method")
    request_id = request.get("id")
    if method == "initialize":
        return result(
            request_id,
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "ahg-construferret-mcp", "version": "0.1.0"},
            },
        )
    if method == "notifications/initialized":
        return result(request_id, {})
    if method == "tools/list":
        return result(request_id, {"tools": TOOLS})
    if method == "tools/call":
        params = request.get("params") or {}
        return result(request_id, call_tool(params.get("name"), params.get("arguments") or {}))
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": -32601, "message": f"Metodo no soportado: {method}"},
    }


def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    if name == "buscar_articulos":
        query = str(arguments.get("query", ""))
        limit = int(arguments.get("limit", 6))
        rows = recommend_products(DB, query, limit=limit)
        DB.log_ai_query(query, len(rows))
        return text_content({"articulos": rows})
    if name == "recomendar_articulos":
        query = str(arguments.get("necesidad", ""))
        budget = arguments.get("presupuesto")
        limit = int(arguments.get("limit", 6))
        rows = recommend_products(DB, query, limit=limit, budget=float(budget) if budget else None)
        DB.log_ai_query(query, len(rows))
        return text_content({"recomendaciones": rows})
    if name == "stock_critico":
        return text_content({"stock_critico": DB.low_stock()})
    raise ValueError(f"Herramienta no soportada: {name}")


def text_content(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "content": [
            {
                "type": "text",
                "text": json.dumps(payload, ensure_ascii=False, indent=2),
            }
        ]
    }


def result(request_id: Any, value: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": value}


if __name__ == "__main__":
    main()
