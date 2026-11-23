# Site da GALO num contêiner. Na raiz do projeto:
#
#   docker build -f site/Dockerfile -t galo-site .
#   docker run -p 8080:8080 galo-site          # abra http://localhost:8080
#
# Não há banco de dados nem arquivos gravados: o contêiner pode ser descartado e recriado à vontade.
FROM python:3.12-slim

WORKDIR /app
COPY galo/ galo/
COPY site/ site/
COPY docs/biblioteca-padrao.md docs/biblioteca-padrao.md

RUN useradd --create-home galo
USER galo

ENV HOST=0.0.0.0 \
    PORT=8080 \
    GALO_PRODUCAO=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

EXPOSE 8080
CMD ["python", "-m", "galo", "executar", "site/servidor.galo"]
