FROM python:3.10-slim

WORKDIR /app

COPY ./app

LABEL org.opencontainers.image.source="https://github.com/nelisiwe04/tender-scrapping"