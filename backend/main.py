import os
import json
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import gspread
from google.oauth2.service_account import Credentials
import pandas as pd
from datetime import date
import requests
from dotenv import load_dotenv

load_dotenv()

GCP_CREDS_JSON = os.getenv("GCP_SERVICE_ACCOUNT_JSON")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID_OR_URL")
SHEET_NAME = os.getenv("SHEET_TAB_NAME")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not all([GCP_CREDS_JSON, SPREADSHEET_ID, SHEET_NAME, GROQ_API_KEY]):
    raise ValueError("ERRO CRÍTICO: Segredos não encontrados. Configure-os nas variáveis de ambiente do Codespace.")

app = FastAPI(title="Focus OS API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup_event():
    try:
        creds_dict = json.loads(GCP_CREDS_JSON)
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(creds)
        spreadsheet = client.open_by_key(SPREADSHEET_ID)
        app.state.worksheet = spreadsheet.worksheet(SHEET_NAME)
        print(">>> SUCESSO: Conexão com Google Sheets estabelecida.")
    except Exception as e:
        app.state.worksheet = None
        print(f">>> FALHA CRÍTICA: Não foi possível conectar ao Google Sheets: {e}")

def get_data_as_dataframe():
    if not hasattr(app.state, 'worksheet') or app.state.worksheet is None:
        raise HTTPException(status_code=503, detail="Serviço indisponível: conexão com a planilha falhou.")
    
    worksheet = app.state.worksheet
    all_values = worksheet.get_all_values()
    if not all_values: return pd.DataFrame()
    
    headers = all_values[0]
    df = pd.DataFrame(all_values[1:], columns=headers)
    df['Data'] = pd.to_datetime(df['Data'], format='%d/%m/%Y', errors='coerce')
    return df

@app.get("/")
def read_root():
    return {"status": "Focus OS API online. Ready for duty."}

@app.get("/tasks/{user}")
def get_today_tasks(user: str):
    try:
        df = get_data_as_dataframe()
        if df.empty: return []
        
        today = date.today()
        df_today = df[df['Data'].dt.date == today]
        df_user_today = df_today[
            (df_today['Aluno(a)'].str.lower() == user.lower()) | 
            (df_today['Aluno(a)'].str.lower() == 'ambos')
        ].fillna('').to_dict('records')
        
        return df_user_today
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class CoachRequest(BaseModel):
    subject: str
    activity: str

@app.post("/coach", response_model=dict)
def get_coach_advice(request: CoachRequest):
    prompt = f'Você é o "System Coach" do Focus OS. Sua missão é gerar um plano tático e 2 flashcards. Responda EXCLUSIVAMENTE em JSON com chaves "summary" e "flashcards" (lista de objetos com "q" e "a"). MISSÃO: Matéria: {request.subject}, Atividade: {request.activity}'
    try:
        headers = {"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"}
        payload = {"model": "gemma2-9b-it", "messages": [{"role": "user", "content": prompt}], "temperature": 0.7, "response_format": {"type": "json_object"}}
        response = requests.post("https://api.groq.com/openai/v1/chat/completions", headers=headers, json=payload, timeout=20)
        response.raise_for_status()
        return json.loads(response.json()['choices'][0]['message']['content'])
    except Exception as e:
        return {"summary": f"// TRANSMISSÃO INTERROMPIDA // Plano de contingência para {request.subject}: Focar nos fundamentos. Revisar por 20min, praticar por 30min.", "flashcards": [{"q": "Principal objetivo?", "a": "Entender o conceito central."}, {"q": "O que evitar?", "a": "Distrações."}]}
