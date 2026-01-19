from typing import Dict, Any, List
from energy.contribution import EnergyContribution


class EnergyValidator:
    MIN_KWH = 0.1
    MAX_KWH = 10000.0
    ALLOWED_SOURCE_PREFIXES = {"solar", "wind", "hydro", "geothermal"}
    
    @staticmethod
    def validate_contribution(contribution: EnergyContribution) -> bool:
        # Basis-Validierung
        if contribution.amount_kwh <= 0:
            return False
        if not contribution.node_id or not contribution.source_id:
            return False
        if not contribution.transaction_hash:
            return False
        
        # Geschäftliche Regeln
        if not (EnergyValidator.MIN_KWH <= contribution.amount_kwh <= EnergyValidator.MAX_KWH):
            return False
        
        # Quellen-Validierung (erlaubt: "solar_panel_1", "wind_turbine_alpha")
        if not any(contribution.source_id.startswith(prefix) for prefix in EnergyValidator.ALLOWED_SOURCE_PREFIXES):
            return False
        
        return True
    
    @staticmethod
    def validate_batch(contributions: List[EnergyContribution]) -> List[EnergyContribution]:
        return [c for c in contributions if EnergyValidator.validate_contribution(c)]