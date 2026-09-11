FROM postgres:16
EXPOSE 5432
WORKDIR /app

COPY ./app

LABEL org.opencontainers.image.source="https://github.com/nelisiwe04/tender-scrapping"