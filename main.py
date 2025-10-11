import os
import re
import json
import logging
import time
from typing import TypeVar, ParamSpec, Callable, cast, Any, Dict, Optional, TypedDict, Union, List, Tuple, Hashable
from typing_extensions import TypeGuard
from fastapi import FastAPI, HTTPException
from fastapi.security import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from pydantic.json import pydantic_encoder
import gspread
from gspread.exceptions import WorksheetNotFound
from google.oauth2.service_account import Credentials
from fastapi import Depends
import pandas as pd
from pandas.core.frame import DataFrame
from pandas.core.series import Series
from datetime import date, datetime, timedelta
import requests
from dotenv import load_dotenv
from functools import wraps

# Type aliases
JsonDict = Dict[str, Any]
SafeDict = Dict[str, Any]

# Environment variable helper
def safe_environ(name: str, required: bool = True) -> str:
    """Get environment variable with proper error handling."""
    value = os.getenv(name)
    if required and not value:
        raise ValueError(f"Required environment variable {name} is not set")
    return cast(str, value)  # We know it's not None here

# Load environment variables with defaults
creds_json = safe_environ('GCP_CREDS_JSON', required=True)
spreadsheet_id = safe_environ('SPREADSHEET_IDENTIFIER', required=True)
sheet_name = safe_environ('SHEET_NAME', required=True)

# Type variables for generic functions
T = TypeVar('T')  # Return type
P = ParamSpec('P')  # Parameters
R = TypeVar('R', covariant=True)  # Return type with covariance

# Custom type aliases for improved type safety
RowType = Dict[str, Any]  # Type for a single row
RecordsType = List[RowType]  # Type for multiple rows

# DataFrame type aliases and helper functions
ValueType = Union[str, int, float, bool, None]
RowDict = Dict[str, ValueType]
RecordsList = List[RowDict]

def normalize_value(value: Any) -> ValueType:
    """Normalize a value to a known type."""
    if pd.isna(value):
        return None
    elif isinstance(value, (int, float, bool)):
        return value
    return str(value)

def convert_series(series: Series) -> RowDict:
    """Convert a pandas Series to a dictionary with normalized types."""
    result: RowDict = {}
    for k, v in series.items():
        key = str(k)
        result[key] = normalize_value(v)
    return result

def clean_series(series: Series, default_value: Any = None) -> Series:
    """Clean a Series by handling NaN values."""
    result = series.copy()
    if pd.isna(default_value):
        result = result.fillna('')
    else:
        result = result.fillna(default_value)
    return result

def clean_dataframe(df: DataFrame) -> DataFrame:
    """Clean a DataFrame by handling NaN values."""
    df_clean = df.copy()
    
    # Handle each column individually
    for col in df_clean.columns:
        if df_clean[col].dtype in ['float64', 'int64']:
            df_clean[col] = df_clean[col].fillna(0)
        else:
            df_clean[col] = df_clean[col].fillna('')
            
    return df_clean

def safe_records(df: DataFrame) -> RecordsList:
    """Convert a DataFrame to a list of dictionaries with normalized types."""
    try:
        df_clean = clean_dataframe(df)
        return [convert_series(row) for _, row in df_clean.iterrows()]
    except Exception as e:
        logging.error(f"Error converting DataFrame to records: {e}")
        return []

def safe_row(df: DataFrame, mask: Series) -> RowDict:
    """Extract a single row from a DataFrame with proper types."""
    try:
        filtered = df[mask]
        if not filtered.empty:
            return convert_series(filtered.iloc[0])
    except Exception as e:
        logging.error(f"Error extracting row from DataFrame: {e}")
    return {}

# Cache system with type safety
CacheKey = str
CacheValue = Any
_cache: Dict[CacheKey, Tuple[CacheValue, float]] = {}

def get_cache(key: CacheKey) -> Optional[CacheValue]:
    """Get a value from cache if it is still valid."""
    if key not in _cache:
        return None
    value, expiry = _cache[key]
    if time.time() > expiry:
        del _cache[key]
        return None
    return value

def set_cache(key: CacheKey, value: CacheValue, ttl: float = 300.0) -> None:
    """Store a value in cache with expiry."""
    _cache[key] = (value, time.time() + ttl)

FuncT = TypeVar('FuncT', bound=Callable[..., Any])

def cached(ttl: float) -> Callable[[FuncT], FuncT]:
    """Cache decorator with TTL (time-to-live)."""
    def decorator(func: FuncT) -> FuncT:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            key = repr((func.__name__, args, kwargs))
            if (cached_result := get_cache(key)) is not None:
                return cached_result
                
            result = func(*args, **kwargs)
            set_cache(key, result, ttl)
            return result
            
        return cast(FuncT, wrapper)
    return decorator

# Load environment variables (from .env when present)
load_dotenv()

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format='[%(asctime)s] %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("focus_os")

# Non-negotiable defaults (act as safe fallbacks if envs are absent)
DEFAULT_SPREADSHEET_ID: str = "1AdMTt9YmJ2QM-We_9NxsEIvW1lJeocLAWBsNbOiDTLE"
DEFAULT_SHEET_NAME: str = "Cronograma e Utilizadores"

# Custom types for improved type safety
EnvStr = str | None

# Environment variables with proper type annotations
GCP_CREDS_JSON: EnvStr = os.getenv("GCP_SERVICE_ACCOUNT_JSON")
SPREADSHEET_IDENTIFIER: str = (
    os.getenv("SPREADSHEET_ID_OR_URL") or 
    os.getenv("SPREADSHEET_ID") or 
    DEFAULT_SPREADSHEET_ID
)
SHEET_NAME: str = os.getenv("SHEET_TAB_NAME") or DEFAULT_SHEET_NAME
GROQ_API_KEY: EnvStr = os.getenv("GROQ_API_KEY")
API_AUTH_TOKEN: EnvStr = os.getenv("API_AUTH_TOKEN")

# DataFrame type aliases for better type hints
DataFrameRow = Dict[str, Any]
DataFrameResult = List[DataFrameRow]

# Validate critical environment variables
missing_vars: List[str] = []
if not GCP_CREDS_JSON:
    missing_vars.append("GCP_SERVICE_ACCOUNT_JSON")
if not GROQ_API_KEY:
    missing_vars.append("GROQ_API_KEY")
if not API_AUTH_TOKEN:
    missing_vars.append("API_AUTH_TOKEN")

if missing_vars:
    raise ValueError(
        f"ERRO CRÍTICO: As seguintes variáveis de ambiente estão ausentes: {', '.join(missing_vars)}"
    )

# Tipos para validação do service account
ServiceAccountDict = Dict[str, str]

# Validate Google Service Account JSON
if GCP_CREDS_JSON is None:
    raise ValueError("GCP_SERVICE_ACCOUNT_JSON não pode ser None")

try:
    creds_dict: ServiceAccountDict = json.loads(GCP_CREDS_JSON)
    required_fields: List[str] = ["type", "project_id", "private_key_id", "private_key", "client_email"]
    missing_fields: List[str] = [field for field in required_fields if field not in creds_dict]
    if missing_fields:
        raise ValueError(f"GCP_SERVICE_ACCOUNT_JSON está incompleto. Campos ausentes: {', '.join(missing_fields)}")
    
    # Validate correct service account
    EXPECTED_EMAIL: str = "eusoufoda@gen-lang-client-0636296115.iam.gserviceaccount.com"
    client_email: Optional[str] = creds_dict.get("client_email")
    if client_email != EXPECTED_EMAIL:
        raise ValueError(f"Service account incorreta. Use a conta: {EXPECTED_EMAIL}")
        
except json.JSONDecodeError:
    raise ValueError("GCP_SERVICE_ACCOUNT_JSON não é um JSON válido")

app = FastAPI(title="Focus OS API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Segurança: Autenticação simples por Header ---
api_key_header = APIKeyHeader(name="X-Focus-Token", auto_error=True)

async def verify_token(token: str = Depends(api_key_header)):
    if token != API_AUTH_TOKEN:
        raise HTTPException(status_code=403, detail="Token inválido ou ausente.")

authed_deps = [Depends(verify_token)]

def _redact(text: Optional[str]) -> str:
    if not text:
        return ""
    if len(text) <= 8:
        return "***"
    return f"{text[:4]}...{text[-4:]}"


def extract_spreadsheet_key(identifier: str) -> str:
    """Return the spreadsheet key whether an ID or full URL was provided."""
    if not identifier:
        return ""
    if identifier.startswith("http"):
        # Try to capture the segment between '/d/' and the next '/'
        match = re.search(r"/d/([a-zA-Z0-9-_]+)", identifier)
        if match:
            return match.group(1)
        # If no match, return as-is; gspread can open_by_url
        return identifier
    return identifier


def init_gsheets_state() -> None:
    """Initialize Google Sheets connection and cache worksheet in app state, with detailed logging."""
    app.state.worksheet = None
    app.state.gs_last_error = None
    try:
        logger.info("Inicializando autenticação com Google usando service account (email mascarado).")
        if not GCP_CREDS_JSON:
            raise ValueError("GCP_CREDS_JSON environment variable is not set")
        creds_dict = json.loads(cast(str, GCP_CREDS_JSON))
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(creds)

        identifier = SPREADSHEET_IDENTIFIER
        key_or_url = extract_spreadsheet_key(identifier)
        logger.info(
            "Conectando ao Spreadsheet: identificador=%s (sheet='%s')",
            _redact(key_or_url),
            SHEET_NAME,
        )

        if key_or_url.startswith("http"):
            spreadsheet = client.open_by_url(key_or_url)
        else:
            spreadsheet = client.open_by_key(key_or_url)

        logger.info("Spreadsheet aberto com sucesso. Enumerando abas disponíveis...")
        available_titles = [ws.title for ws in spreadsheet.worksheets()]
        logger.info("Abas encontradas: %s", ", ".join(available_titles))

        try:
            worksheet = spreadsheet.worksheet(SHEET_NAME)
        except WorksheetNotFound:
            logger.error(
                "Aba '%s' não encontrada. Verifique o nome exato. Abas disponíveis: %s",
                SHEET_NAME,
                ", ".join(available_titles),
            )
            raise

        app.state.worksheet = worksheet
        logger.info("Conexão com a aba '%s' estabelecida.", worksheet.title)
    except Exception as e:
        app.state.gs_last_error = str(e)
        app.state.worksheet = None
        logger.exception("Falha ao conectar ao Google Sheets: %s", e)



@cached(ttl=60) # Cache de 60 segundos
def get_data_as_dataframe() -> pd.DataFrame:
    if not hasattr(app.state, "worksheet") or app.state.worksheet is None:
        raise HTTPException(
            status_code=503,
            detail="Serviço indisponível: conexão com a planilha falhou. Consulte /status para detalhes.",
        )
    worksheet = app.state.worksheet
    logger.info("Solicitando dados da planilha '%s' via get_all_values()...", worksheet.title)
    all_values = worksheet.get_all_values()
    logger.info("Linhas retornadas (incl. cabeçalho): %d", len(all_values))
    if not all_values:
        return pd.DataFrame()
    headers = all_values[0]
    df = pd.DataFrame(all_values[1:], columns=headers)
    if "Data" in df.columns:
        df["Data"] = pd.to_datetime(df["Data"], format="%d/%m/%Y", errors="coerce")
    else:
        logger.warning("Coluna 'Data' não encontrada na planilha. Datas serão ignoradas.")
    _cache.pop("get_sheet_snapshot", None) # Invalida cache dependente
    return df

def _get_user_row_data(date_obj: date, user: str) -> Optional[Dict[str, Any]]:
    """Helper to get all data for a specific user and date."""
    df = get_data_as_dataframe()
    if df.empty:
        return None
    
    mask = (df["Data"].dt.date == date_obj) & (
        df["Aluno(a)"].str.lower() == user.lower()
    )
    
    if not mask.any():
        # Check for 'ambos' if no specific user row found
        mask_ambos = (df["Data"].dt.date == date_obj) & (
            df["Aluno(a)"].str.lower() == 'ambos'
        )
        if mask_ambos.any():
            return df[mask_ambos].iloc[0].to_dict()
        return None
    return df[mask].iloc[0].to_dict()

def _get_sheet_snapshot() -> Tuple[List[str], List[List[str]]]:
    """Return (headers, rows) from the cached worksheet. Rows exclude header row."""
    if not hasattr(app.state, "worksheet") or app.state.worksheet is None:
        raise HTTPException(status_code=503, detail="Serviço indisponível: planilha offline.")
    worksheet = app.state.worksheet
    all_values = worksheet.get_all_values()
    if not all_values:
        return [], []
    headers = all_values[0]
    _cache.pop(f"cached_dataframe", None) # Invalida o cache do dataframe principal
    return headers, all_values[1:]


def _find_row_index_for(date_obj: date, user: str) -> Optional[int]:
    """Return 1-based sheet row index for the data row (including header offset)."""
    df = get_data_as_dataframe()
    if df.empty:
        return None
    if "Data" not in df.columns or "Aluno(a)" not in df.columns:
        return None
    mask = (df["Data"].dt.date == date_obj) & (
        df["Aluno(a)"].str.lower() == user.lower()
    )
    if not mask.any():
        return None
    # DataFrame index is zero-based for data rows (excluding header). Sheet rows add 2 (header + 1-indexing).
    idx0 = int(df[mask].index[0])
    return idx0 + 2


def _ensure_row_for(date_obj: date, user: str) -> int:
    """Ensure a row exists for (date, user). Return 1-based row index."""
    row_idx = _find_row_index_for(date_obj, user)
    if row_idx is not None:
        return row_idx

    if not hasattr(app.state, "worksheet") or app.state.worksheet is None:
        raise HTTPException(status_code=503, detail="Serviço indisponível: planilha offline.")

    worksheet = app.state.worksheet
    headers, rows = _get_sheet_snapshot()
    header_to_pos: Dict[str, int] = {h: i + 1 for i, h in enumerate(headers)}

    # Build a new row with defaults according to known columns
    new_row: List[str] = [""] * len(headers)
    if "Data" in header_to_pos:
        new_row[header_to_pos["Data"] - 1] = date_obj.strftime("%d/%m/%Y")
    if "Aluno(a)" in header_to_pos:
        new_row[header_to_pos["Aluno(a)"] - 1] = user
    if "Dia da Semana" in header_to_pos:
        # Use pt-BR short weekday names
        day_name = [
            "Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"
        ][(date_obj.weekday()) % 7]
        new_row[header_to_pos["Dia da Semana"] - 1] = day_name

    # Append and compute the new row index (header row is 1)
    for attempt in range(3):
        try:
            worksheet.append_row(new_row, value_input_option="USER_ENTERED")
            # Row index is header (1) + number of existing data rows before append + 1
            return 1 + len(rows) + 1
        except Exception as e:
            if attempt == 2:
                logger.exception("Falha ao inserir nova linha: %s", e)
                raise HTTPException(status_code=500, detail="Falha ao inserir linha no Sheets.")
            time.sleep(0.4 * (attempt + 1))
    
    # This should never be reached as the loop above either returns or raises an exception
    raise RuntimeError("Unreachable code")


def _safe_update_cells(row_index: int, updates: Dict[str, Any]) -> None:
    """Update multiple header-named cells in a given row with lightweight retries."""
    if not hasattr(app.state, "worksheet") or app.state.worksheet is None:
        raise HTTPException(status_code=503, detail="Serviço indisponível: planilha offline.")
    worksheet = app.state.worksheet
    headers, _ = _get_sheet_snapshot()
    if not headers:
        raise HTTPException(status_code=500, detail="Planilha sem cabeçalho.")
    header_to_pos: Dict[str, int] = {h: i + 1 for i, h in enumerate(headers)}

    # Prepare cell updates; ignore unknown headers gracefully
    cell_updates: List[Tuple[int, int, Any]] = []
    for header, value in updates.items():
        if header in header_to_pos:
            cell_updates.append((row_index, header_to_pos[header], value))
        else:
            logger.debug("Cabeçalho não encontrado, ignorando update: %s", header)

    for (r, c, v) in cell_updates:
        for attempt in range(3):
            try:
                worksheet.update_cell(r, c, v)
                break
            except Exception as e:
                if attempt == 2:
                    logger.exception("Falha ao atualizar célula r=%s c=%s: %s", r, c, e)
                    raise HTTPException(status_code=500, detail="Falha ao atualizar a planilha.")
                time.sleep(0.4 * (attempt + 1))

@app.get("/")
def read_root():
    return {"status": "Focus OS API online. Ready for duty."}

@app.get("/tasks/{user}", dependencies=authed_deps)
def get_today_tasks(user: str) -> List[Dict[str, Any]]:
    try:
        df = get_data_as_dataframe()
        if df.empty: return []
        
        today = date.today()
        df_today = df[df.get('Data', pd.Series(dtype='datetime64[ns]')).dt.date == today] if 'Data' in df.columns else df
        if 'Aluno(a)' in df_today.columns:
            df_user_today = df_today[
                (df_today['Aluno(a)'].str.lower() == user.lower()) |
                (df_today['Aluno(a)'].str.lower() == 'ambos')
            ]
        else:
            df_user_today = df_today
        df_user_today = df_user_today.fillna('').to_dict('records')
        
        # Convert to the expected type
        return cast(List[Dict[str, Any]], df_user_today)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class OracleBriefingRequest(BaseModel):
    user: str
    date_str: Optional[str] = None # dd/mm/yyyy
    period: str # Manhã, Tarde, Noite

@app.post("/oracle-briefing", response_model=dict, dependencies=authed_deps)
def get_oracle_briefing(request: OracleBriefingRequest):
    target_date = (
        datetime.strptime(request.date_str, "%d/%m/%Y").date() if request.date_str else date.today()
    )
    
    row_data = _get_user_row_data(target_date, request.user)
    
    if not row_data:
        return {"briefing": f"Olá, {request.user}. Nenhuma missão encontrada para {target_date.strftime('%d/%m')}. Aproveite o dia!"}

    # Extract relevant data for the AI prompt
    subject_key = f"Matéria ({request.period})"
    activity_key = f"Atividade Detalhada ({request.period})"
    
    subject = row_data.get(subject_key, "N/A")
    activity = row_data.get(activity_key, "N/A")
    difficulty = row_data.get("Dificuldade (1-5)", "não informada")
    alert_comment = row_data.get("Alerta/Comentário", "nenhum comentário anterior")
    priority = row_data.get("Prioridade", "não definida")
    
    # Construct a detailed prompt for the AI
    prompt = (
        f"Você é o Oráculo do Focus OS, um mentor estratégico para estudantes de medicina. "
        f"Sua missão é fornecer um briefing motivacional e tático para o operador {request.user}, "
        f"focando na missão de {request.period} para {target_date.strftime('%d/%m/%Y')}. "
        f"A missão é: Matéria '{subject}' - Atividade '{activity}'.\n\n"
        f"Contexto do Operador:\n"
        f"- Dificuldade reportada anteriormente: {difficulty}\n"
        f"- Alerta/Comentário anterior: '{alert_comment}'\n"
        f"- Prioridade atual: '{priority}'\n\n"
        f"Com base nesses dados, crie um parágrafo estratégico e inspirador. "
        f"Inclua uma análise do comentário anterior, um foco tático para a missão e reforce a prioridade. "
        f"Seja conciso, direto e com um tom de voz de um mentor experiente. "
        f"Exemplo: 'Bom dia, Mateus. Sua missão da manhã é Matemática - Geometria Espacial. Da última vez, seu comentário foi 'confuso com o cálculo de volume de cones'. Alerta da IA: Foque na dedução da fórmula, não na memorização. Sua prioridade hoje é Precisão. Execute com excelência.'"
    )

    try:
        headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": "gemma2-9b-it", "messages": [{"role": "user", "content": prompt}], "temperature": 0.7, "max_tokens": 300}
        response = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=15)
        response.raise_for_status()
        briefing_text = response.json()['choices'][0]['message']['content']
        return {"briefing": briefing_text}
    except Exception as e:
        logger.error("Falha na chamada à IA Groq para briefing: %s", e)
        return {"briefing": f"Olá, {request.user}. Sua missão de {request.period} é '{subject}' - '{activity}'. Mantenha o foco e boa sorte!"}

class MindMeldRequest(BaseModel):
    subject: str
    activity: str
    last_comment: Optional[str] = "Nenhum"

@app.post("/mind-meld", response_model=dict, dependencies=authed_deps)
def get_mind_meld_insight(request: MindMeldRequest):
    prompt = (
        f"URGENTE: Meu operador está em apuros com {request.subject} - {request.activity}. "
        f"O último Alerta/Comentário dele foi '{request.last_comment}'. "
        "Ignore explicações genéricas. Forneça três novas perspectivas radicais para entender este conceito "
        "e uma única pergunta desafiadora que o force a pensar diferente. "
        "Aja como um mentor socrático, não como um livro didático. "
        "Responda em texto simples, direto ao ponto."
    )
    try:
        headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": "gemma2-9b-it", "messages": [{"role": "user", "content": prompt}], "temperature": 0.8, "max_tokens": 400}
        response = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=20)
        response.raise_for_status()
        return {"insight": response.json()['choices'][0]['message']['content']}
    except Exception as e:
        logger.error("Falha na chamada à IA Groq para MIND MELD: %s", e)
        return {"insight": "// TRANSMISSÃO DE EMERGÊNCIA INTERROMPIDA // Recalibre. Respire fundo. Qual é a pergunta mais fundamental que você ainda não fez sobre este tópico?"}

class CoachRequest(BaseModel):
    subject: str
    activity: str

@app.post("/coach", response_model=dict, dependencies=authed_deps)
def get_coach_advice(request: CoachRequest):
    prompt = f'Você é o "System Coach" do Focus OS. Sua missão é gerar um plano tático e 2 flashcards. Responda EXCLUSIVAMENTE em JSON com chaves "summary" e "flashcards" (lista de objetos com "q" e "a"). MISSÃO: Matéria: {request.subject}, Atividade: {request.activity}'
    try:
        headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": "gemma2-9b-it", "messages": [{"role": "user", "content": prompt}], "temperature": 0.7, "response_format": {"type": "json_object"}}
        response = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=15)
        response.raise_for_status()
        return json.loads(response.json()['choices'][0]['message']['content'])
    except Exception as e:
        logger.error("Falha na chamada à IA Groq: %s", e)
        return {"summary": f"// TRANSMISSÃO INTERROMPIDA // Plano de contingência para {request.subject}: Focar nos fundamentos. Revisar por 20min, praticar por 30min.", "flashcards": [{"q": "Principal objetivo?", "a": "Entender o conceito central."}, {"q": "O que evitar?", "a": "Distrações."}]}


@app.on_event("startup")
def on_startup() -> None:
    logger.info("Iniciando Focus OS API...")
    # Initialize Google Sheets
    init_gsheets_state()

    # Probe IA availability (non-fatal)
    app.state.ia_online = False
    try:
        headers = {"Authorization": f"Bearer {GROQ_API_KEY}"}
        resp = requests.get("https://api.groq.com/openai/v1/models", headers=headers, timeout=8)
        app.state.ia_online = resp.ok
        logger.info("IA Groq online: %s", app.state.ia_online)
    except Exception as e:
        logger.warning("Não foi possível verificar IA Groq: %s", e)


@app.get("/status")
def status() -> dict:
    sheet_ok = hasattr(app.state, "worksheet") and app.state.worksheet is not None
    last_error = getattr(app.state, "gs_last_error", None)
    worksheet_title = app.state.worksheet.title if sheet_ok else None
    return {
        "sheet": {
            "online": sheet_ok,
            "worksheet": worksheet_title,
            "identifier": _redact(extract_spreadsheet_key(SPREADSHEET_IDENTIFIER)),
            "last_error": last_error,
        },
        "ia": {
            "online": bool(getattr(app.state, "ia_online", False)),
            "model": "gemma2-9b-it",
        },
    }


# ---------- New Endpoints: /ask, /summary/{user}, /update_progress, /update_meta, /history/{user}

class AskRequest(BaseModel):
    topic: str
    count: Optional[int] = 3
    mode: Optional[str] = "mixed"  # mcq | truefalse | mixed


@app.post("/ask", response_model=dict, dependencies=authed_deps)
def ask_quiz(req: AskRequest) -> dict:
    count = min(max(req.count or 3, 3), 5)
    mode = req.mode if req.mode in {"mcq", "truefalse", "mixed"} else "mixed"
    system_prompt = (
        "Gere perguntas curtas para revisão médica. Responda EM JSON. Estrutura: "
        "{\"questions\":[{\"type\":\"mcq|truefalse\",\"question\":\"...\",\"options\":[\"A\",\"B\",...],\"answer\":\"A|true|false\",\"explanation\":\"...\"}]}"
    )
    user_prompt = (
        f"Tópico: {req.topic}. Quantidade: {count}. Modo: {mode}. "
        "Se 'mcq', inclua 4 opções. Priorize alta qualidade e clareza."
    )
    try:
        headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
        payload = {
            "model": "gemma2-9b-it",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.7,
            "response_format": {"type": "json_object"},
        }
        response = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=15)
        response.raise_for_status()
        data = json.loads(response.json()["choices"][0]["message"]["content"])  # type: ignore[index]
        # Normalize shape for frontend robustness
        questions = data.get("questions") or []
        normalized = []
        for q in questions:
            qtype = "truefalse" if str(q.get("type", "")).lower() == "truefalse" else "mcq"
            ans = str(q.get("answer", "")).strip().lower()
            if qtype == "truefalse":
                ans = "true" if ans in {"true", "verdadeiro", "v"} else "false"
            normalized.append({
                "type": qtype,
                "question": str(q.get("question", "")),
                "options": q.get("options"),
                "answer": ans if qtype == "truefalse" else q.get("answer"),
                "explanation": q.get("explanation"),
            })
        return {"questions": normalized}
    except Exception as e:
        logger.warning("Falha no /ask (fallback): %s", e)
        # Fallback simples
        sample = {
            "questions": [
                {
                    "type": "truefalse",
                    "question": "A hemoglobina transporta oxigênio no sangue.",
                    "answer": "true",
                    "explanation": "A hemoglobina dos eritrócitos se liga ao O2 nos pulmões.",
                },
                {
                    "type": "mcq",
                    "question": "Qual válvula separa átrio esquerdo do ventrículo esquerdo?",
                    "options": ["Pulmonar", "Aórtica", "Mitral", "Tricúspide"],
                    "answer": "Mitral",
                    "explanation": "A válvula mitral (bicúspide) fica entre átrio e ventrículo esquerdos.",
                },
                {
                    "type": "mcq",
                    "question": "Principal local de absorção de nutrientes?",
                    "options": ["Estômago", "Duodeno/Jejuno", "Íleo terminal", "Cólon"],
                    "answer": "Duodeno/Jejuno",
                    "explanation": "A maior parte da absorção ocorre no intestino delgado proximal.",
                },
            ][:count]
        }
        return sample


@app.get("/summary/{user}", dependencies=authed_deps)
def get_summary(user: str) -> Dict[str, Any]:
    try:
        df = get_data_as_dataframe()
        if df.empty:
            return {"insights": "Sem dados para hoje.", "stats": {}}

        today = date.today()
        # Filter
        aluno_series = df.get("Aluno(a)", pd.Series("", index=df.index)).astype(str)
        df_user = df[(aluno_series.str.lower() == user.lower()) | (aluno_series.str.lower() == "ambos")]
        df_recent = df_user.copy()
        if "Data" in df_recent.columns:
            df_recent = df_recent.sort_values("Data", ascending=False)

        # Today stats
        df_today = df_recent[df_recent["Data"].dt.date == today] if "Data" in df_recent.columns else pd.DataFrame()
        pct = None
        diff = None
        status = None
        alert = None
        if not df_today.empty:
            # Try to parse % Concluído (may contain % sign)
            if "% Concluído" in df_today.columns:
                val = str(df_today.iloc[0]["% Concluído"]).strip().replace("%", "")
                pct = int(float(val)) if val.replace(".", "", 1).isdigit() else None
            if "Dificuldade (1-5)" in df_today.columns:
                try:
                    diff_val = df_today.iloc[0]["Dificuldade (1-5)"]
                    diff = int(float(str(diff_val) if pd.notnull(diff_val) else "0"))
                except Exception:
                    diff = None
            if "Status" in df_today.columns:
                status = str(df_today.iloc[0]["Status"]).strip()
            if "Alerta/Comentário" in df_today.columns:
                alert = str(df_today.iloc[0]["Alerta/Comentário"]).strip()

        insights = []
        if pct is not None:
            insights.append(f"Progresso de hoje: {pct}%")
        if diff is not None:
            insights.append(f"Dificuldade percebida: {diff}/5")
        if status:
            insights.append(f"Status: {status}")
        if alert:
            insights.append(f"Alerta: {alert}")
        if not insights:
            insights.append("Mantenha o foco nas prioridades de hoje.")

        return {
            "insights": " • ".join(insights),
            "stats": {
                "today_percent": pct,
                "today_difficulty": diff,
                "today_status": status,
                "today_alert": alert,
            },
        }
    except Exception as e:
        logger.exception("Erro em /summary: %s", e)
        raise HTTPException(status_code=500, detail="Falha ao gerar resumo.")


class UpdateProgressRequest(BaseModel):
    user: str
    date_str: Optional[str] = None  # dd/mm/yyyy
    questoes_planejadas: Optional[int] = None
    questoes_feitas: Optional[int] = None
    teoria_feita: Optional[bool] = None
    percentual_concluido: Optional[int] = None
    status: Optional[str] = None


@app.post("/update_progress", dependencies=authed_deps)
def update_progress(body: UpdateProgressRequest) -> Dict[str, Any]:
    try:
        if not body.user:
            raise HTTPException(status_code=400, detail="Parâmetro 'user' é obrigatório.")
        target_date = (
            datetime.strptime(body.date_str, "%d/%m/%Y").date() if body.date_str else date.today()
        )
        row_idx = _ensure_row_for(target_date, body.user)

        updates: Dict[str, Any] = {}
        # Map into sheet columns when present
        if body.questoes_planejadas is not None:
            updates["Questões Planejadas"] = body.questoes_planejadas
        if body.questoes_feitas is not None:
            updates["Questões Feitas"] = body.questoes_feitas
        # Support combined column if present
        if body.questoes_planejadas is not None or body.questoes_feitas is not None:
            headers, _ = _get_sheet_snapshot()
            if "Questões Planejadas/Feitas" in headers:
                qp = body.questoes_planejadas if body.questoes_planejadas is not None else ""
                qf = body.questoes_feitas if body.questoes_feitas is not None else ""
                updates["Questões Planejadas/Feitas"] = f"{qp}/{qf}"

        if body.teoria_feita is not None:
            updates["Teoria Feita"] = "Sim" if body.teoria_feita else "Não"
        if body.percentual_concluido is not None:
            val = max(0, min(100, int(body.percentual_concluido)))
            updates["% Concluído"] = f"{val}%"
        if body.status is not None:
            updates["Status"] = body.status

        if not updates:
            raise HTTPException(status_code=400, detail="Nenhum campo de progresso para atualizar.")

        _safe_update_cells(row_idx, updates)
        return {"ok": True, "row": row_idx}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Erro em /update_progress: %s", e)
        raise HTTPException(status_code=500, detail="Falha ao atualizar progresso.")


class UpdateMetaRequest(BaseModel):
    user: str
    date_str: Optional[str] = None
    dificuldade: Optional[int] = None  # 1-5
    prioridade: Optional[str] = None
    situacao: Optional[str] = None
    alerta: Optional[str] = None
    fase_plano: Optional[str] = None


@app.post("/update_meta", dependencies=authed_deps)
def update_meta(body: UpdateMetaRequest) -> Dict[str, Any]:
    try:
        if not body.user:
            raise HTTPException(status_code=400, detail="Parâmetro 'user' é obrigatório.")
        target_date = (
            datetime.strptime(body.date_str, "%d/%m/%Y").date() if body.date_str else date.today()
        )
        row_idx = _ensure_row_for(target_date, body.user)

        updates: Dict[str, Any] = {}
        if body.dificuldade is not None:
            value = max(1, min(5, int(body.dificuldade)))
            updates["Dificuldade (1-5)"] = value
        if body.prioridade is not None:
            updates["Prioridade"] = body.prioridade
        if body.situacao is not None:
            # Some sheets may use 'Situação' with cedilla
            updates["Situação"] = body.situacao
            updates["Situacao"] = body.situacao  # fallback header variant
        if body.alerta is not None:
            updates["Alerta/Comentário"] = body.alerta
        if body.fase_plano is not None:
            updates["Fase do Plano"] = body.fase_plano

        if not updates:
            raise HTTPException(status_code=400, detail="Nenhum campo de meta para atualizar.")

        _safe_update_cells(row_idx, updates)
        return {"ok": True, "row": row_idx}
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Erro em /update_meta: %s", e)
        raise HTTPException(status_code=500, detail="Falha ao atualizar metas.")


@app.get("/history/{user}", dependencies=authed_deps)
def history(user: str) -> Dict[str, List[Dict[str, Any]]]:
    try:
        df = get_data_as_dataframe()
        if df.empty:
            return {"history": []}
        # Filter by user or 'Ambos'
        aluno_series = df.get("Aluno(a)", pd.Series("", index=df.index)).astype(str)
        mask_user = (aluno_series.str.lower() == user.lower()) | (aluno_series.str.lower() == "ambos")
        df_user = df[mask_user].copy()
        if "Data" not in df_user.columns:
            return {"history": []}
        # Keep last 14 days including today
        start_date = date.today() - timedelta(days=13)
        df_user = df_user[(df_user["Data"].dt.date >= start_date) & (df_user["Data"].dt.date <= date.today())]
        # Build records
        records: List[Dict[str, Any]] = []
        for _, row in df_user.sort_values("Data").iterrows():
            pct_val = None
            if "% Concluído" in df_user.columns:
                raw = str(row.get("% Concluído", "")).strip().replace("%", "")
                try:
                    pct_val = int(float(raw))
                except Exception:
                    pct_val = None
            diff_val = None
            if "Dificuldade (1-5)" in df_user.columns:
                try:
                    value = row.get("Dificuldade (1-5)", "")
                    diff_val = int(float(str(value) if pd.notnull(value) else "0"))
                except Exception:
                    diff_val = None
            records.append({
                "date": row["Data"].strftime("%d/%m"),
                "percent": pct_val,
                "difficulty": diff_val,
            })
        return {"history": records}
    except Exception as e:
        logger.exception("Erro em /history: %s", e)
        raise HTTPException(status_code=500, detail="Falha ao obter histórico.")
