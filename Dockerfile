FROM python:3.7-slim-stretch

WORKDIR /app

RUN groupadd --gid 10001 app \
    && useradd -m -g app --uid 10001 -s /usr/sbin/nologin app

RUN apt-get update && \
    apt-get install --yes build-essential && \
    pip install --progress-bar=off -U pip && \
    apt-get -q --yes autoremove && \
    apt-get clean && \
    rm -rf /root/.cache

COPY ./requirements /app/requirements
COPY ./checks/remotesettings/requirements.txt /app/checks/remotesettings/requirements.txt

# No deps on the remotesettings requirements because it includes kinto-signer,
# which depends on Pyramid. We don't want all of Pyramid.
RUN pip install --progress-bar=off -r requirements/default.txt && \
    pip install --progress-bar=off --no-deps -r checks/remotesettings/requirements.txt

COPY . /app

RUN touch /app/config.toml

ENV PYTHONPATH=/app
ENV HOST=0.0.0.0
ENV PORT=8000
EXPOSE 8000

# run as non priviledged user
USER app

ENTRYPOINT ["/app/scripts/run.sh"]
CMD ["server"]
