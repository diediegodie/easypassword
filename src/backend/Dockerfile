FROM python:3.12-alpine

WORKDIR /app

# Instalar dependências do sistema
RUN apk add --no-cache gcc musl-dev postgresql-dev

# Copiar requirements e instalar dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código da aplicação
COPY . .

# Expor porta
EXPOSE 8000

# Comando padrão
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
