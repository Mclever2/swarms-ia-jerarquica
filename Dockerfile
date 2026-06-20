FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libgomp1 \
    ca-certificates \
    curl \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# torch CPU-only FIRST (evita ~1.8 GB de CUDA)
RUN pip install --no-cache-dir \
    "numpy<2" \
    torch==2.5.1+cpu \
    --extra-index-url https://download.pytorch.org/whl/cpu

# Dependencias Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Pre-descarga del modelo HuggingFace (queda bakeado en la imagen)
RUN python -c "\
from langchain_huggingface import HuggingFaceEmbeddings; \
HuggingFaceEmbeddings(model_name='intfloat/multilingual-e5-small', model_kwargs={'device': 'cpu'})"

# Codigo fuente + chroma_db/ (libros pre-indexados localmente) + books/
# .dockerignore excluye: venv/, .env, __pycache__/, .git/, outputs/
COPY . .

RUN mkdir -p /app/outputs /app/agent_workspace

# Bloquea descargas de HuggingFace en runtime (modelo ya bakeado)
ENV TRANSFORMERS_OFFLINE=1
ENV HF_DATASETS_OFFLINE=1

ENV PORT=8080
ENV STREAMLIT_SERVER_MAX_UPLOAD_SIZE=200
ENV STREAMLIT_SERVER_ENABLE_WEBSOCKET_COMPRESSION=false
EXPOSE 8080

CMD ["python", "-m", "streamlit", "run", "frontend/app.py", \
     "--server.port=8080", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--server.enableCORS=false", \
     "--server.enableXsrfProtection=false", \
     "--server.maxUploadSize=200", \
     "--server.fileWatcherType=none"]
