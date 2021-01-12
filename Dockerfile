FROM python:3.8-slim-buster

WORKDIR /app

RUN groupadd --gid 10001 app \
    && useradd -m -g app --uid 10001 -s /usr/sbin/nologin app

RUN apt-get update && \
    apt-get install --yes build-essential curl && \
    pip install --progress-bar=off -U pip && \
    apt-get -q --yes autoremove && \
    apt-get clean && \
    rm -rf /root/.cache

COPY ./requirements /app/requirements
COPY ./checks/remotesettings/requirements.txt /app/checks/remotesettings/requirements.txt

RUN pip install --progress-bar=off -r requirements/default.txt && \
    pip install --progress-bar=off -r checks/remotesettings/requirements.txt

COPY . /app


ENV PYTHONPATH=/app
ENV HOST=0.0.0.0
ENV PORT=8000
EXPOSE 8000

# run as non priviledged user
USER app

ENTRYPOINT ["/app/scripts/run.sh"]
CMD ["server"]
