from pydantic import BaseModel
from enum import Enum
from datetime import datetime
from typing import Optional


class TipoTreino(str, Enum):
    Z2_LONGO    = "Z2_LONGO"
    TIROS       = "TIROS"
    VO2MAX      = "VO2MAX"
    TEMPO       = "TEMPO"
    FORCA       = "FORCA"
    ACADEMIA    = "ACADEMIA"
    RECUPERACAO = "RECUPERACAO"
    DESCANSO    = "DESCANSO"


class ResultadoTreino(BaseModel):
    garmin_activity_id: Optional[str] = None
    fit_file: Optional[str] = None
    duracao_min: Optional[int] = None
    distancia_km: Optional[float] = None
    elevacao_m: Optional[float] = None
    avg_hr: Optional[int] = None
    max_hr: Optional[int] = None
    cadencia_media_rpm: Optional[int] = None
    cadencia_max_rpm: Optional[int] = None
    calorias: Optional[int] = None
    analise_ia: Optional[dict] = None


class Treino(BaseModel):
    data: Optional[datetime] = None
    tipo: TipoTreino
    periodo: Optional[str] = None   # manha | meio_dia | tarde | noite
    duracao_min: int
    distancia_km: Optional[float] = None
    elevacao_m: Optional[float] = None
    calorias: Optional[int] = None
    descricao: Optional[str] = None


class Refeicao(BaseModel):
    horario: str
    nome: str
    itens: list[str]
    kcal_estimado: int
    proteina_g: float
    carbo_g: float
    gordura_g: float
    observacao: Optional[str] = None


class PlanoAlimentar(BaseModel):
    data: datetime
    treino: Optional[Treino] = None
    tipo_dia: str
    kcal_total: int
    proteina_total_g: float
    refeicoes: list[Refeicao]
