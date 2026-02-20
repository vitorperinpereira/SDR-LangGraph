import random
from datetime import datetime, timedelta

def get_available_slots():
    """Simula a obtencao de horarios disponiveis."""
    now = datetime.now()
    
    # Gera horarios aleatorios para hoje e amanha (sempre horario comercial)
    
    # Slot 1: Amanha as 10:00 ou 14:00
    tomorrow = now + timedelta(days=1)
    slot1_hour = random.choice([10, 14, 16])
    slot1_time = tomorrow.replace(hour=slot1_hour, minute=0, second=0, microsecond=0)
    
    # Slot 2: Depois de amanha as 09:00 ou 15:00
    after_tomorrow = now + timedelta(days=2)
    slot2_hour = random.choice([9, 11, 15])
    slot2_time = after_tomorrow.replace(hour=slot2_hour, minute=0, second=0, microsecond=0)
    
    return [
        {"start": slot1_time.isoformat(), "end": (slot1_time + timedelta(hours=1)).isoformat()},
        {"start": slot2_time.isoformat(), "end": (slot2_time + timedelta(hours=1)).isoformat()}
    ]
