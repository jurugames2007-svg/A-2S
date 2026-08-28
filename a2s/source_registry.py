"""Selector operativo y trazable para fuentes declaradas de Aegis.

Este módulo solo consulta metadatos locales. No descarga, importa ni ejecuta
ninguna fuente externa; una recomendación siempre requiere una acción
posterior explícita del operador.
"""

from __future__ import annotations

import json
import re
from dataclasses import replace
from typing import Any, Optional

from .recursos import (FuenteExterna, SourceRegistry as _CatalogRegistry,
                       _norm, _source_from_entry, _todas)


class SourceRegistry(_CatalogRegistry):
    """Registro de fuentes con consulta de capacidades y recomendaciones."""

    def register_capability(self, source_id: str, capability: str) -> FuenteExterna:
        """Añade una capacidad declarada sin cambiar la política de la fuente."""
        source = self.get(source_id)
        value = capability.strip()
        if not value:
            raise ValueError("capability debe ser texto no vacío")
        if value in source.capabilities:
            return source
        updated = replace(source, capabilities=tuple(sorted((*source.capabilities, value))))
        self.register(updated)
        return updated

    def capabilities(self, source_id: str = "", categoria: str = "") -> list[dict[str, Any]]:
        """Consulta capacidades declaradas, ordenadas de forma estable."""
        sources = self.search(categoria=categoria) if categoria else self._sources.values()
        rows = []
        for source in sorted(sources, key=lambda item: item.id):
            if source_id and source.id != source_id:
                continue
            for capability in sorted(source.capabilities):
                rows.append({"source": source.id, "capability": capability,
                             "category": source.categoria, "policy": source.policy})
        return rows

    def select_tools(self, goal: str, categoria: str = "", limit: Optional[int] = None,
                     include_reference_only: bool = False) -> dict[str, Any]:
        """Recomienda fuentes por objetivo/categoría sin efectos externos.

        ``selected`` contiene únicamente entradas con política ``allowed``.
        Las demás coincidencias se conservan como trazabilidad de la decisión;
        ``include_reference_only`` se mantiene por compatibilidad y no altera
        la frontera de seguridad del selector.
        """
        if not isinstance(goal, str) or not goal.strip():
            raise ValueError("goal debe ser texto no vacío")
        query = _norm(goal)
        terms = set(re.findall(r"[a-z0-9]+", query))
        category = _norm(categoria).strip()
        selected: list[dict[str, Any]] = []
        reference_only: list[dict[str, Any]] = []
        blocked: list[dict[str, Any]] = []
        for source in sorted(self._sources.values(), key=lambda item: item.id):
            if category and _norm(source.categoria) != category:
                continue
            matches = []
            for capability in source.capabilities:
                normalized = _norm(capability).replace("_", " ")
                overlap = sorted(set(re.findall(r"[a-z0-9]+", normalized)) & terms)
                if normalized in query or overlap:
                    matches.append((capability, overlap))
            if not matches:
                continue
            matched = sorted({item[0] for item in matches})
            overlap_terms = sorted({term for _, values in matches for term in values})
            exact = any(_norm(capability).replace("_", " ") in query
                        for capability, _ in matches)
            score = (100 if exact else 0) + len(overlap_terms) * 10 + len(matched)
            row = {
                "source": source.id, "name": source.nombre, "url": source.url,
                "category": source.categoria, "capabilities": matched,
                "dependencies": source.dependencia, "policy": source.policy,
                "adapter_status": source.adapter_status, "score": score,
                "score_breakdown": {"exact_capability": 100 if exact else 0,
                                    "matching_terms": len(overlap_terms) * 10,
                                    "matched_capabilities": len(matched)},
                "reason": ("capacidad coincidente; fuente autorizada y adapter verificado"
                           if source.policy == "allowed" and source.adapter_status == "verified"
                           else "coincidencia declarativa; decisión basada en la política registrada"),
            }
            if source.policy == "blocked":
                blocked.append({**row, "exclusion_reason": "fuente bloqueada por política"})
            elif source.policy == "reference_only":
                reference_only.append({**row, "exclusion_reason": "fuente solo de referencia"})
            else:
                selected.append(row)
        for rows in (selected, reference_only, blocked):
            rows.sort(key=lambda row: (-row["score"], row["source"]))
        if limit is not None:
            if limit < 0:
                raise ValueError("limit no puede ser negativo")
            selected = selected[:limit]
        excluded = sorted((*reference_only, *blocked),
                          key=lambda row: (-row["score"], row["source"]))
        return {"goal": goal, "category": categoria, "selected": selected,
            "reference_only": reference_only, "blocked": blocked,
            "excluded": excluded}

    def serialize_selection(self, selection: dict[str, Any]) -> str:
        """Serializa una recomendación conservando un orden reproducible."""
        return json.dumps(selection, ensure_ascii=True, indent=2, sort_keys=True)


def source_registry(workspace: str = "") -> SourceRegistry:
    """Construye el selector desde el catálogo local y recursos del workspace."""
    return SourceRegistry(_source_from_entry(entry, workspace)
                          for entry in _todas(workspace) if entry.get("url"))


def select_tools(goal: str, categoria: str = "", workspace: str = "",
                 limit: Optional[int] = None,
                 include_reference_only: bool = False) -> dict[str, Any]:
    """Atajo para recomendar fuentes declaradas desde un workspace."""
    return source_registry(workspace).select_tools(
        goal, categoria, limit, include_reference_only)