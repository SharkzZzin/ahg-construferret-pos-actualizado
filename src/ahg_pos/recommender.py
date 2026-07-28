from __future__ import annotations

import math
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any


SPELLING_FIXES = {
    "acttualizar": "actualizar",
    "arituclos": "articulos",
    "busqeda": "busqueda",
    "bucqueda": "busqueda",
    "calinte": "caliente",
    "conctreto": "concreto",
    "exitencia": "existencia",
    "exixtencia": "existencia",
    "fugga": "fuga",
    "martiyo": "martillo",
    "pinturra": "pintura",
    "taladdro": "taladro",
    "tornio": "tornillo",
    "tuvberia": "tuberia",
    "tuberai": "tuberia",
    "varriya": "varilla",
    "prefactura": "Pre-Factura",
}

STOPWORDS = {
    "a",
    "al",
    "alta",
    "algo",
    "con",
    "de",
    "del",
    "el",
    "en",
    "la",
    "las",
    "lo",
    "los",
    "me",
    "mi",
    "necesito",
    "para",
    "por",
    "que",
    "quiero",
    "busco",
    "dame",
    "recomiendame",
    "sirve",
    "solucion",
    "cliente",
    "reparar",
    "hacer",
    "comprar",
    "usar",
    "se",
    "tiene",
    "una",
    "un",
    "y",
    "rd",
    "rds",
    "peso",
    "pesos",
    "pieza",
    "piezas",
    "barato",
    "economico",
    "rapido",
    "urgente",
}

SYNONYMS = {
    "filtracion": {"humedad", "grieta", "fuga", "sellador", "techo", "junta"},
    "filtra": {"filtracion", "fuga", "sellador"},
    "grieta": {"sellador", "fuga", "filtracion", "junta"},
    "fuga": {"tuberia", "sellador", "cpvc", "pvc", "pegamento"},
    "agua": {"tuberia", "plomeria", "pvc", "cpvc"},
    "caliente": {"cpvc", "alta", "temperatura", "pegamento"},
    "fria": {"pvc", "sanitario", "tuberia"},
    "tubo": {"tuberia", "pvc", "cpvc"},
    "tuberia": {"tubo", "pvc", "cpvc", "plomeria"},
    "electricidad": {"cable", "breaker", "circuito", "tomacorriente"},
    "tomacorriente": {"cable", "breaker", "circuito", "thhn"},
    "concreto": {"cemento", "taladro", "broca", "varilla"},
    "columna": {"cemento", "varilla", "estructura"},
    "losa": {"cemento", "varilla", "estructura"},
    "pintar": {"pintura", "acrilica", "pared"},
    "pared": {"pintura", "acrilica", "sellador"},
    "metal": {"disco", "corte", "varilla", "tornillo"},
    "cortar": {"disco", "corte", "herramienta"},
    "perforar": {"taladro", "broca", "herramienta"},
    "enchufe": {"tomacorriente", "cable", "breaker", "electricidad"},
    "corriente": {"electricidad", "cable", "breaker", "circuito"},
    "cementar": {"cemento", "mezcla", "construccion"},
    "pegar": {"pegamento", "adhesivo", "union"},
    "oxido": {"metal", "pintura", "proteccion"},
    "impermeabilizar": {"sellador", "filtracion", "humedad", "techo"},
    "humedad": {"sellador", "filtracion", "pintura", "pared"},
    "gotera": {"sellador", "filtracion", "techo"},
    "baño": {"pvc", "cpvc", "plomeria", "tuberia", "sanitario"},
    "bano": {"pvc", "cpvc", "plomeria", "tuberia", "sanitario"},
    "cocina": {"pvc", "cpvc", "plomeria", "tuberia"},
    "instalar": {"herramienta", "taladro", "tornillo", "cable", "tuberia"},
    "fijar": {"tornillo", "hexagonal", "soporte"},
    "atornillar": {"tornillo", "taladro", "herramienta"},
    "obra": {"cemento", "varilla", "construccion", "estructura"},
    "terminacion": {"pintura", "sellador", "acabado"},
    "acabado": {"pintura", "sellador", "pared"},
    "proteccion": {"breaker", "seguridad", "circuito"},
    "calinte": {"caliente", "cpvc", "temperatura"},
    "calor": {"caliente", "cpvc", "temperatura"},
    "plomero": {"plomeria", "tuberia", "pvc", "cpvc"},
    "albanil": {"cemento", "varilla", "construccion"},
    "maestro": {"cemento", "varilla", "construccion", "herramienta"},
    "vivienda": {"residencial", "electricidad", "plomeria"},
    "casa": {"residencial", "electricidad", "plomeria", "pintura"},
    "negocio": {"comercial", "electricidad", "seguridad"},
    "aire": {"acondicionado", "ventilacion", "extractor", "filtro"},
    "climatizar": {"acondicionado", "ventilacion", "termostato"},
    "ventilar": {"ventilador", "extractor", "ventilacion"},
    "lluvia": {"techo", "canaleta", "bajante", "drenaje", "impermeable"},
    "puerta": {"cerradura", "bisagra", "cerrojo", "manija"},
    "cerrar": {"cerradura", "cerrojo", "puerta"},
    "limpiar": {"limpieza", "desengrasante", "cepillo", "trapeador"},
    "sucio": {"limpieza", "desengrasante", "cepillo"},
    "carro": {"automotriz", "motor", "bateria", "aceite"},
    "vehiculo": {"automotriz", "motor", "bateria", "aceite"},
    "seguridad": {"casco", "guante", "proteccion", "chaleco"},
    "proteger": {"proteccion", "casco", "guante", "respirador"},
}

PHRASE_HINTS = {
    "agua caliente": {"cpvc", "alta", "temperatura", "pegamento"},
    "agua fria": {"pvc", "sanitario"},
    "corto circuito": {"breaker", "cable", "electricidad"},
    "tomacorriente": {"breaker", "cable", "thhn"},
    "techo filtracion": {"sellador", "humedad", "grieta"},
    "tuberia empotrada": {"cpvc", "pvc", "pegamento"},
    "instalacion electrica": {"cable", "breaker", "circuito", "electricidad"},
    "cortar metal": {"disco", "corte", "metal", "herramienta"},
    "perforar concreto": {"taladro", "broca", "concreto", "herramienta"},
    "filtracion techo": {"sellador", "humedad", "grieta"},
    "pared humeda": {"sellador", "pintura", "humedad"},
    "instalar tomacorriente": {"cable", "breaker", "electricidad"},
    "refuerzo estructural": {"varilla", "cemento", "estructura"},
    "instalar breaker": {"breaker", "cable", "proteccion", "electricidad"},
    "cambiar enchufe": {"tomacorriente", "cable", "electricidad"},
    "preparar mezcla": {"cemento", "construccion"},
    "pintar pared": {"pintura", "acabado", "pared"},
    "sellar techo": {"sellador", "filtracion", "techo"},
    "aire acondicionado": {"inverter", "btu", "cobre", "aislante"},
    "agua de lluvia": {"canaleta", "bajante", "drenaje"},
    "seguridad personal": {"casco", "guante", "chaleco", "proteccion"},
    "cambiar aceite": {"aceite", "motor", "automotriz"},
    "cerrar puerta": {"cerradura", "cerrojo", "bisagra"},
}

COMPLEMENT_HINTS = {
    "cpvc": {"pegamento", "tubo"},
    "pvc": {"pegamento", "tubo"},
    "tubo": {"pegamento", "sellador"},
    "cemento": {"varilla"},
    "varilla": {"cemento", "disco"},
    "taladro": {"broca", "tornillo"},
    "breaker": {"cable"},
    "cable": {"breaker"},
    "pintura": {"sellador"},
    "sellador": {"pintura"},
    "disco": {"metal"},
}


def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.lower()
    return re.sub(r"[^a-z0-9/ ]+", " ", value)


def required_filter_questions(query: str) -> list[str]:
    """Return mandatory questions before recommending a product by assumption."""
    normalized = normalize(query)
    questions: list[str] = []

    is_pipe = any(term in normalized for term in ("tubo", "tuberia", "pvc", "cpvc", "plomeria"))
    if is_pipe:
        has_diameter = bool(
            re.search(r"\b\d+\s*/\s*\d+\b|\b\d+(?:[.,]\d+)?\s+pulgada(?:s)?\b", normalized)
        ) or any(term in normalized for term in ("media pulgada", "tres cuartos", "una pulgada"))
        if not has_diameter:
            questions.append("\u00bfQu\u00e9 di\u00e1metro o medida necesita el tubo?")
        if not any(term in normalized for term in ("pvc", "cpvc", "ppr", "cobre", "metal", "hierro", "acero")):
            questions.append("\u00bfDe qu\u00e9 material debe ser el tubo?")
        if not any(term in normalized for term in ("fria", "caliente", "sanitaria", "potable", "drenaje")):
            questions.append("\u00bfEs para agua fr\u00eda, caliente, potable o drenaje?")

    if any(term in normalized for term in ("pintura", "pintar")):
        if not any(term in normalized for term in ("blanco", "negro", "rojo", "azul", "verde", "amarillo", "gris", "beige", "color")):
            questions.append("\u00bfQu\u00e9 color necesita?")
        if not any(term in normalized for term in ("interior", "exterior")):
            questions.append("\u00bfSe usar\u00e1 en interior o exterior?")
        if not any(term in normalized for term in ("galon", "cubeta", "litro", "litros")):
            questions.append("\u00bfLa necesita por gal\u00f3n, cubeta o litro?")

    return questions


def reformulate_query(query: str) -> str:
    words = re.split(r"(\W+)", (query or "").strip())
    corrected: list[str] = []
    for word in words:
        key = normalize(word).strip()
        replacement = SPELLING_FIXES.get(key)
        if replacement:
            corrected.append(replacement.upper() if word.isupper() else replacement)
        else:
            corrected.append(word)
    cleaned = re.sub(r"\s+", " ", "".join(corrected)).strip()
    return cleaned[:1].upper() + cleaned[1:] if cleaned else ""


def tokenize(text: str) -> list[str]:
    return [token for token in normalize(text).split() if token and token not in STOPWORDS]


def expand_query(query: str) -> set[str]:
    normalized = normalize(query)
    tokens = {SPELLING_FIXES.get(token, token).lower() for token in tokenize(query)}
    expanded = set(tokens)
    for token in tokens:
        expanded.update(SYNONYMS.get(token, set()))
        expanded.update(word_variants(token))
    for phrase, hints in PHRASE_HINTS.items():
        if phrase in normalized:
            expanded.update(hints)
    if any(word in normalized for word in ("ventilar", "ventilacion", "extractor")):
        expanded.difference_update({"pvc", "cpvc", "plomeria", "tuberia", "sanitario"})
        expanded.update({"ventilador", "extractor", "ventilacion"})
    if "lluvia" in normalized:
        expanded.difference_update({"pvc", "cpvc", "plomeria", "tuberia", "sanitario"})
        expanded.update({"techo", "canaleta", "bajante", "drenaje", "impermeable"})
    return expanded


def word_variants(token: str) -> set[str]:
    """Expand common Spanish catalog forms without making the query noisy."""
    variants: set[str] = set()
    if len(token) > 4 and token.endswith("es"):
        variants.add(token[:-2])
    elif len(token) > 3 and token.endswith("s"):
        variants.add(token[:-1])
    elif len(token) > 3:
        variants.add(f"{token}s")
    return variants


def recommend_products(db: Any, query: str, limit: int = 6, budget: float | None = None) -> list[dict[str, Any]]:
    query = (query or "").strip()
    if not query:
        return []
    products = db.list_products()
    terms = expand_query(query)
    ranked: list[dict[str, Any]] = []
    for product in products:
        if not bool(product.get("active", True)) or float(product["stock"]) <= 0:
            continue
        price = float(product["price"])
        if budget and price > budget:
            continue
        score, matched = score_product(product, terms, query)
        if score < 3 or not matched:
            continue
        item = dict(product)
        item["score"] = round(score, 3)
        item["confidence"] = min(99, round(35 + score * 3.2, 1))
        item["matched_terms"] = sorted(matched)
        item["reason"] = build_reason(item, matched, query)
        item["need_type"] = classify_need(query, matched, item)
        item["stock_note"] = stock_note(item)
        item["sales_tip"] = sales_tip(item, matched)
        item["complements"] = suggest_complements(item, products)
        item["advisor_summary"] = advisor_summary(query, item, matched)
        item["questions"] = advisor_questions(query, item, matched)
        item["compatibility_notes"] = compatibility_notes(query, item, matched)
        item["decision_label"] = decision_label(item)
        ranked.append(item)

    ranked.sort(key=lambda row: (row["score"], float(row["stock"])), reverse=True)
    return ranked[: max(1, min(int(limit), 20))]


def suggest_ai_guidance(
    db: Any,
    query: str = "",
    recommendations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    query = reformulate_query(query)
    products = [row for row in db.list_products() if bool(row.get("active", True)) and float(row.get("stock") or 0) > 0]
    categories = sorted({str(row.get("category", "")).strip() for row in products if row.get("category")})
    terms = expand_query(query)
    keywords = sorted(terms)[:10]
    inventory_matches = inventory_answer(products, query, terms)
    category_matches = [
        category for category in categories
        if any(term and term in normalize(category) for term in terms)
    ][:5]
    if not category_matches:
        category_matches = categories[:5]
    samples = build_search_examples(category_matches)
    return {
        "quick_prompts": [
            "Reparar fuga de agua caliente empotrada",
            "Instalar tomacorriente con proteccion",
            "Pintar pared con humedad",
            "Perforar concreto para fijar soporte",
            "Preparar mezcla para reparacion pequena",
        ],
        "guided_questions": [
            "Que problema quiere resolver el cliente?",
            "Donde se usara: interior, exterior, agua, electricidad o estructura?",
            "Que medida, voltaje, amperaje, diametro o cantidad conoce?",
            "Tiene presupuesto maximo o busca la opcion mas completa?",
        ],
        "search_suggestions": samples,
        "category_hints": category_matches,
        "interpreted_keywords": keywords,
        "inventory_answer": inventory_matches,
        "reformulated_query": query,
        "follow_up_prompt": build_follow_up_prompt(query, keywords, inventory_matches),
        "result_summary": summarize_recommendations(recommendations or [], query),
    }


def summarize_recommendations(recommendations: list[dict[str, Any]], query: str = "") -> str:
    """Return one short, factual line derived only from available results."""
    if not recommendations:
        return "No encontre articulos disponibles; prueba con el nombre, uso o medida." 
    return "Estos fueron los resultados mas afinados conforme a tu inventario."


def format_quantity(value: float) -> str:
    return str(int(value)) if value.is_integer() else f"{value:g}"


def inventory_answer(products: list[dict[str, Any]], query: str, terms: set[str]) -> list[dict[str, Any]]:
    normalized = normalize(query)
    if not any(word in normalized for word in ("stock", "inventario", "existencia", "disponible", "hay")) and len(terms) < 2:
        return []
    rows: list[dict[str, Any]] = []
    for product in products:
        text = normalize(
            f"{product.get('name', '')} {product.get('sku', '')} {product.get('category', '')} {product.get('tags', '')}"
        )
        matched = [term for term in terms if term in text]
        if matched:
            rows.append({
                "name": product.get("name", ""),
                "sku": product.get("sku", ""),
                "stock": product.get("stock", 0),
                "min_stock": product.get("min_stock", 0),
                "price": product.get("price", 0),
                "matched_terms": matched[:4],
            })
    rows.sort(key=lambda item: (len(item["matched_terms"]), float(item["stock"] or 0)), reverse=True)
    return rows[:5]


def build_follow_up_prompt(query: str, keywords: list[str], inventory_rows: list[dict[str, Any]]) -> str:
    if not query.strip():
        return "Escribe el problema, uso, medida o material que busca el cliente."
    if inventory_rows:
        return "Puedo responder stock, precio y alternativas. Confirma medida, marca o uso para afinar la recomendacion."
    if len(keywords) < 2:
        return "No entendi suficiente contexto. Indica material, medida, problema y donde se usara."
    return "Si la recomendacion no es exacta, dime medida, marca, ambiente de uso o presupuesto."


def build_search_examples(categories: list[str]) -> list[str]:
    defaults = [
        "tuberia pvc 1/2 para agua fria",
        "breaker y cable para circuito residencial",
        "sellador para filtracion de techo",
        "broca para concreto y tornillos",
        "cemento y varilla para columna",
    ]
    examples: list[str] = []
    for category in categories:
        normalized = normalize(category)
        if "plomer" in normalized or "tuber" in normalized:
            examples.append("tuberia o pegamento para fuga de agua")
        elif "electric" in normalized or "cable" in normalized:
            examples.append("cable, breaker o tomacorriente para instalacion")
        elif "pint" in normalized or "sell" in normalized:
            examples.append("pintura o sellador para pared humeda")
        elif "cement" in normalized or "constru" in normalized:
            examples.append("cemento, varilla o mezcla para obra")
        elif "herramient" in normalized:
            examples.append("herramienta para perforar, cortar o fijar")
    return dedupe(examples + defaults)[:6]


def decision_label(product: dict[str, Any]) -> str:
    confidence = float(product.get("confidence") or 0)
    stock = float(product.get("stock") or 0)
    minimum = float(product.get("min_stock") or 0)
    if confidence >= 80 and (minimum <= 0 or stock > minimum):
        return "recomendado"
    if confidence >= 65:
        return "revisar medida"
    return "alternativa"


def classify_need(query: str, matched: set[str], product: dict[str, Any]) -> str:
    normalized = normalize(query)
    matched_normalized = {normalize(term) for term in matched}
    category = normalize(product.get("category", ""))
    if any(term in normalized for term in ("fuga", "filtracion", "grieta", "gotera", "humedad")):
        return "reparacion"
    if any(term in normalized for term in ("instalar", "instalacion", "tomacorriente", "circuito")):
        return "instalacion"
    if any(term in normalized for term in ("obra", "columna", "losa", "estructura")) or "cemento" in category:
        return "construccion"
    if any(term in normalized for term in ("pintar", "acabado", "terminacion")):
        return "acabado"
    if "corte" in matched_normalized or "perforacion" in matched_normalized:
        return "herramienta"
    return "venta general"


def stock_note(product: dict[str, Any]) -> str:
    stock = float(product.get("stock") or 0)
    minimum = float(product.get("min_stock") or 0)
    if stock <= minimum:
        return "Stock bajo: conviene confirmar disponibilidad antes de prometer entrega."
    if stock <= minimum * 2 and minimum > 0:
        return "Stock moderado: disponible, pero cerca del minimo."
    return "Disponible para venta inmediata."


def sales_tip(product: dict[str, Any], matched: set[str]) -> str:
    price = float(product.get("price") or 0)
    cost = float(product.get("cost") or 0)
    margin = ((price - cost) / price * 100) if price > 0 and cost >= 0 else 0
    if "circuito" in matched:
        return "Pregunta amperaje, distancia del cableado y uso del circuito antes de cerrar la venta."
    if "agua caliente" in matched:
        return "Confirma si la instalacion es para agua caliente; CPVC y adhesivo compatible deben venderse juntos."
    if "sellado" in matched:
        return "Pregunta si la superficie estara expuesta a agua, sol o movimiento para elegir sellador correcto."
    if margin >= 25:
        return "Buena opcion comercial por margen y disponibilidad."
    return "Confirma medida, material y cantidad antes de facturar."


def advisor_summary(query: str, product: dict[str, Any], matched: set[str]) -> str:
    need = classify_need(query, matched, product)
    label = decision_label(product)
    if label == "recomendado":
        return f"Buena respuesta para una necesidad de {need}; coincide tecnicamente y tiene disponibilidad."
    if label == "revisar medida":
        return f"Puede resolver la necesidad de {need}, pero conviene validar medida, material o uso exacto."
    return f"Alternativa disponible para {need}; usala si el cliente confirma compatibilidad."


def advisor_questions(query: str, product: dict[str, Any], matched: set[str]) -> list[str]:
    normalized = normalize(query)
    text = normalize(
        f"{product.get('name', '')} {product.get('category', '')} {product.get('technical_description', '')} {product.get('tags', '')}"
    )
    questions: list[str] = []
    if any(term in normalized or term in text for term in ("tuberia", "pvc", "cpvc", "plomeria")):
        questions.extend(["¿Es para agua fria o caliente?", "¿Que diametro o medida necesita?"])
    if any(term in normalized or term in text for term in ("cable", "breaker", "tomacorriente", "electricidad")):
        questions.extend(["¿Que amperaje requiere?", "¿La instalacion es residencial o comercial?"])
    if any(term in normalized or term in text for term in ("cemento", "varilla", "concreto", "estructura")):
        questions.extend(["¿Es reparacion pequena u obra estructural?", "¿Cuantos metros o unidades usara?"])
    if any(term in normalized or term in text for term in ("pintura", "sellador", "humedad", "filtracion")):
        questions.extend(["¿La superficie estara expuesta a agua o sol?", "¿Es interior o exterior?"])
    if not questions:
        questions.append("¿Que medida, cantidad y uso final necesita el cliente?")
    return dedupe(questions)[:3]


def compatibility_notes(query: str, product: dict[str, Any], matched: set[str]) -> list[str]:
    normalized = normalize(query)
    text = normalize(
        f"{product.get('name', '')} {product.get('category', '')} {product.get('technical_description', '')} {product.get('tags', '')}"
    )
    notes: list[str] = []
    if "agua caliente" in normalized and "cpvc" in text:
        notes.append("Compatible con agua caliente si se usa adhesivo CPVC.")
    if "agua caliente" in normalized and "pvc" in text and "cpvc" not in text:
        notes.append("Cuidado: para agua caliente normalmente conviene CPVC.")
    if "breaker" in text or "cable" in text:
        notes.append("Valida amperaje y calibre antes de vender.")
    if "sellador" in text:
        notes.append("Verifica superficie, humedad y tiempo de secado.")
    if "taladro" in text or "broca" in text:
        notes.append("Confirma el material a perforar.")
    return dedupe(notes)[:3]


def dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        key = normalize(value)
        if key and key not in seen:
            result.append(value)
            seen.add(key)
    return result


def suggest_complements(product: dict[str, Any], products: list[dict[str, Any]]) -> list[str]:
    text = normalize(
        f"{product.get('name', '')} {product.get('sku', '')} {product.get('category', '')} "
        f"{product.get('technical_description', '')} {product.get('tags', '')}"
    )
    desired: set[str] = set()
    for key, hints in COMPLEMENT_HINTS.items():
        if key in text:
            desired.update(hints)
    if not desired:
        return []
    suggestions: list[str] = []
    current_id = str(product.get("id", ""))
    for candidate in products:
        if str(candidate.get("id", "")) == current_id or float(candidate.get("stock") or 0) <= 0:
            continue
        candidate_text = normalize(
            f"{candidate.get('name', '')} {candidate.get('sku', '')} {candidate.get('category', '')} "
            f"{candidate.get('technical_description', '')} {candidate.get('tags', '')}"
        )
        if any(hint in candidate_text for hint in desired):
            suggestions.append(str(candidate.get("name", "")))
        if len(suggestions) >= 3:
            break
    return suggestions


def score_product(product: dict[str, Any], terms: set[str], raw_query: str) -> tuple[float, set[str]]:
    name = normalize(product["name"])
    description = normalize(product["technical_description"])
    tags = normalize(product.get("tags", ""))
    category = normalize(product.get("category", ""))
    sku = normalize(product.get("sku", ""))
    barcode = normalize(product.get("barcode", ""))
    product_id = normalize(product.get("id", ""))
    extra = normalize(
        f"{product.get('brand', '')} {product.get('unit_name', '')} "
        f"{product.get('location', '')} {product.get('supplier', '')}"
    )
    vocabulary = set(tokenize(f"{name} {description} {tags} {category} {extra}"))
    matched: set[str] = set()
    score = 0.0
    normalized_query = normalize(raw_query).strip()

    if normalized_query and normalized_query in {sku, barcode, product_id}:
        return 35.0, {normalized_query}
    if any(code and code in normalized_query for code in (sku, barcode, product_id)):
        score += 18
        matched.add("código exacto")

    for term in terms:
        term_score = 0.0
        if term in name:
            term_score += 4.0
        if term in tags:
            term_score += 3.0
        if term in description:
            term_score += 2.0
        if term in category:
            term_score += 1.0
        if term in extra:
            term_score += 1.5
        if term in sku or term in barcode or term in product_id:
            term_score += 8.0
        if not term_score and len(term) >= 4:
            similar = best_similar_term(term, vocabulary)
            if similar:
                term_score += 1.5
                matched.add(f"{term}≈{similar}")
        if term_score:
            matched.add(term)
            score += term_score

    if "agua caliente" in normalized_query and "cpvc" in tags:
        score += 7
        matched.add("agua caliente")
    if ("grieta" in normalized_query or "filtracion" in normalized_query or "fuga" in normalized_query) and (
        "sellador" in tags or "pegamento" in tags
    ):
        score += 5
        matched.add("sellado")
    if ("tomacorriente" in normalized_query or "circuito" in normalized_query) and (
        "cable" in tags or "breaker" in tags
    ):
        score += 5
        matched.add("circuito")
    if ("cortar" in normalized_query or "corte" in normalized_query) and "disco" in tags:
        score += 5
        matched.add("corte")
    if ("perforar" in normalized_query or "agujero" in normalized_query) and "taladro" in tags:
        score += 5
        matched.add("perforación")
    product_text = f"{name} {description} {tags} {category}"
    if any(word in normalized_query for word in ("ventilar", "ventilacion", "calor")) and any(
        word in product_text for word in ("ventilador", "extractor", "ventilacion", "aire acondicionado")
    ):
        score += 14
        matched.add("ventilacion")
    if any(word in normalized_query for word in ("lluvia", "gotera", "techo")) and any(
        word in product_text for word in ("techo", "canaleta", "bajante", "impermeable", "manto asfaltico")
    ):
        score += 14
        matched.add("proteccion de techo")
    if any(word in normalized_query for word in ("puerta", "cerrar", "seguro")) and any(
        word in product_text for word in ("cerradura", "cerrojo", "bisagra", "puerta")
    ):
        score += 12
        matched.add("puerta")
    if any(word in normalized_query for word in ("carro", "vehiculo", "motor", "bateria")) and "automotriz" in product_text:
        score += 12
        matched.add("automotriz")
    if any(word in normalized_query for word in ("polvo", "proteger", "proteccion")) and any(
        word in product_text for word in ("mascarilla", "respirador", "casco", "proteccion personal")
    ):
        score += 12
        matched.add("proteccion personal")
    if matched:
        if float(product["stock"]) <= float(product["min_stock"]):
            score -= 1.5
        score += math.log(float(product["stock"]) + 1) / 5
    return score, matched


def best_similar_term(term: str, vocabulary: set[str]) -> str:
    best = ""
    best_ratio = 0.0
    for candidate in vocabulary:
        if abs(len(candidate) - len(term)) > 3:
            continue
        ratio = SequenceMatcher(None, term, candidate).ratio()
        if ratio > best_ratio:
            best = candidate
            best_ratio = ratio
    return best if best_ratio >= 0.78 else ""


def build_reason(product: dict[str, Any], matched: set[str], query: str) -> str:
    if "código exacto" in matched or normalize(query).strip() in {
        normalize(product.get("id", "")),
        normalize(product.get("sku", "")),
        normalize(product.get("barcode", "")),
    }:
        return "Coincidencia directa por código, referencia o código de barras."
    if "agua caliente" in matched and "cpvc" in normalize(product["name"]):
        return "Recomendado para conduccion de agua caliente y reparaciones empotradas."
    if "sellado" in matched:
        return "Coincide con una necesidad de sellado, fuga, grieta o filtracion."
    if "circuito" in matched:
        return "Aplica para trabajos electricos residenciales y proteccion de circuitos."
    if "corte" in matched:
        return "Adecuado para la tarea de corte indicada y compatible con trabajo en metal."
    if "perforación" in matched:
        return "Adecuado para perforación según el material descrito en la consulta."
    if matched:
        terms = ", ".join(sorted(list(matched))[:4])
        return f"Coincide con la consulta por: {terms}."
    return "Producto disponible con relacion tecnica cercana a la solicitud."
