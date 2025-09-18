# Usando a imagem oficial do PostgreSQL
FROM postgres:15

# Variáveis de ambiente para configuração inicial
ENV POSTGRES_DB=mydatabase
ENV POSTGRES_USER=myuser
ENV POSTGRES_PASSWORD=mypassword

# Copiar scripts SQL (opcional, para inicialização do DB)
# COPY ./init.sql /docker-entrypoint-initdb.d/

EXPOSE 5432
