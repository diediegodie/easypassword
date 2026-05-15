FROM python:3.12-alpine

WORKDIR /app

# Instalar dependências do sistema
RUN apk add --no-cache gcc musl-dev postgresql-dev

# Copiar requirements e instalar dependências Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código da aplicação
COPY . .

# Copiar e configurar entrypoint script
COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

# Expor porta
EXPOSE 8000

# Entrypoint script que executa migrações e inicia a aplicação
ENTRYPOINT ["/app/entrypoint.sh"]
