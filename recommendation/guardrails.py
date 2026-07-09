"""Guardrails de lenguaje (sección 20): nunca frases absolutas o impositivas."""
import logging
import re

logger = logging.getLogger(__name__)

REPLACEMENT = "[expresión removida por política de prudencia]"

# Frases prohibidas por la sección 20 (case-insensitive)
FORBIDDEN_PATTERNS = [
    r"compra\s+segur[ao]",
    r"compra\s+garantizad[ao]",
    r"gananci\w*\s+garantizad\w*",
    r"retorno\s+(garantizado|asegurado)",
    r"beneficio\s+garantizado",
    r"esta\s+acci[oó]n\s+va\s+a\s+subir",
    r"va\s+a\s+subir\s+seguro",
    r"no\s+hay\s+riesgo",
    r"sin\s+(ning[uú]n\s+)?riesgo",
    r"libre\s+de\s+riesgo",
    r"imposible\s+perder",
    r"100%\s+seguro",
    r"guaranteed\s+(gains?|returns?|profits?)",
    r"risk[-\s]free",
    r"can'?t\s+lose",
]

_COMPILED = [re.compile(p, re.IGNORECASE) for p in FORBIDDEN_PATTERNS]


def contains_forbidden_phrases(text: str) -> list[str]:
    """Devuelve las coincidencias prohibidas encontradas en el texto."""
    found = []
    for pattern in _COMPILED:
        for match in pattern.finditer(text or ""):
            found.append(match.group(0))
    return found


def sanitize_text(text: str) -> tuple[str, list[str]]:
    """Reemplaza frases absolutas prohibidas antes de persistir (sección 5.2
    punto 4). Devuelve (texto saneado, lista de frases removidas)."""
    removed = contains_forbidden_phrases(text)
    sanitized = text or ""
    for pattern in _COMPILED:
        sanitized = pattern.sub(REPLACEMENT, sanitized)
    if removed:
        logger.warning("Guardrail sección 20: frases removidas %s", removed)
    return sanitized, removed
