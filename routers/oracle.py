from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Optional, List
import httpx
from datetime import datetime
import asyncio
import json
import os

# Configuração
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY environment variable is not set")

router = APIRouter()

class TaskContext(BaseModel):
    subject: str
    activity: str
    difficulty: int
    comment: Optional[str]
    priority: str

class OracleBriefing(BaseModel):
    message: str
    tactical_focus: List[str]
    performance_insight: str
    completion_estimate: int

@router.post("/oracle/briefing")
async def get_oracle_briefing(context: TaskContext):
    try:
        # Construir um prompt personalizado e empático
        prompt = f"""
        Você é o Oráculo do Focus OS, um mentor estratégico para {context.subject}.
        
        CONTEXTO DA MISSÃO:
        - Matéria: {context.subject}
        - Atividade: {context.activity}
        - Dificuldade Reportada: {context.difficulty}/10
        - Último Comentário: {context.comment or 'Nenhum comentário anterior'}
        - Prioridade: {context.priority}
        
        Com base nestes dados, gere:
        1. Uma mensagem motivacional e estratégica personalizada
        2. Três focos táticos específicos para esta sessão
        3. Uma análise de performance baseada no histórico
        4. Uma estimativa de conclusão (em porcentagem)
        
        Formato: JSON
        """
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.groq.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {GROQ_API_KEY}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": "gemma2-9b-it",
                    "messages": [
                        {"role": "system", "content": "Você é o Oráculo, um mentor estratégico do Focus OS."},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.7,
                    "max_tokens": 500,
                    "response_format": {"type": "json_object"}
                },
                timeout=10.0
            )
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Erro ao se comunicar com a IA: {response.text}"
                )
                
            result = response.json()
            briefing_data = json.loads(result['choices'][0]['message']['content'])
            
            return OracleBriefing(
                message=briefing_data['message'],
                tactical_focus=briefing_data['tactical_focus'],
                performance_insight=briefing_data['performance_insight'],
                completion_estimate=briefing_data['completion_estimate']
            )
            
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Tempo limite excedido ao consultar a IA")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro interno: {str(e)}")

# Middleware para tratamento de erros
@router.middleware("http")
async def error_handler(request, call_next):
    try:
        return await call_next(request)
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"detail": "O Oráculo está temporariamente indisponível. Tente novamente em alguns momentos."}
        )