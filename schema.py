from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Literal, Optional

TipoEntrada = Literal["receita_contrato", "receita_pipeline", "custo_projetado", "custo_realizado"]
Confianca = Literal["alta", "media", "baixa"]
BU = Literal["BR", "US"]

@dataclass
class CashflowEntry:
    periodo: str          # "2025-06"
    bu: BU
    tipo: TipoEntrada
    categoria: str
    valor_brl: float
    probabilidade: float  # 1.0 para OMIE/RP; 0.0-1.0 para pipeline
    fonte: str            # "pipeline_br" | "pipeline_us" | "omie" | "rp_bi"
    confianca: Confianca
    cliente: Optional[str] = None
    descricao: Optional[str] = None
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self):
        return asdict(self)

    def valor_ponderado(self) -> float:
        return self.valor_brl * self.probabilidade


PIPELINE_BR_PROB = {
    "prospecção": 0.10,
    "qualificação": 0.20,
    "proposta": 0.40,
    "negociação": 0.70,
    "contrato enviado": 0.85,
    "fechado": 1.00,
}

PIPELINE_US_PROB = {
    "prospecting": 0.10,
    "qualification": 0.20,
    "proposal": 0.40,
    "negotiation": 0.70,
    "contract sent": 0.85,
    "closed won": 1.00,
}
