FROM python:3.11-slim-buster

WORKDIR /app

RUN groupadd --gid 10001 app \
    && useradd -m -g app --uid 10001 -s /usr/sbin/nologin app

RUN apt-get update && \
    apt-get install --yes build-essential curl && \
    pip install --progress-bar=off -U pip && \
    pip install poetry && \
    apt-get -q --yes autoremove && \
    apt-get clean && \
    rm -rf /root/.cache

COPY ./pyproject.toml /app
COPY ./poetry.lock /app

COPY . /app

ENV HOST=0.0.0.0
ENV PORT=8000
EXPOSE 8000

# run as non priviledged user
USER app

RUN poetry install --with remotesettings,taskcluster --without dev --no-ansi --no-interaction --verbose

ENTRYPOINT ["/app/bin/run.sh"]
CMD ["server"]
