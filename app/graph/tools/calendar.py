from typing import Any, Dict, List

from langchain_core.tools import tool

from app.clinicorp_sim import get_available_slots
from app.gcal import gcal_service


@tool("buscar_horarios_disponiveis")
def buscar_horarios_disponiveis(periodo: str = "", limit: int = 2) -> List[Dict[str, str]]:
    """Retorna opcoes de horarios disponiveis para o agendamento."""
    slots = get_available_slots()
    safe_limit = max(1, min(int(limit), len(slots) if slots else 1))
    lowered_periodo = (periodo or "").lower()
    
    def _hour(slot: Dict[str, str]) -> int:
        return int(slot["start"][11:13])

    if "manha" in lowered_periodo:
        filtered = [slot for slot in slots if _hour(slot) < 12]
    elif "tarde" in lowered_periodo:
        filtered = [slot for slot in slots if _hour(slot) >= 12]
    else:
        filtered = slots

    selected = list(filtered) if filtered else list(slots)
    if len(selected) < safe_limit:
        for slot in slots:
            if slot not in selected:
                selected.append(slot)
            if len(selected) >= safe_limit:
                break
    return selected[:safe_limit]


@tool("criar_evento_agenda")
def criar_evento_agenda(summary: str, start_time: str, end_time: str, description: str = "") -> Dict[str, Any]:
    """Cria um evento no Google Calendar para confirmar o agendamento."""
    return gcal_service.create_event(
        summary=summary,
        start_time=start_time,
        end_time=end_time,
        description=description,
    )
