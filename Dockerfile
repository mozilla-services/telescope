FROM python:3.7-slim-stretch

WORKDIR /app

RUN groupadd --gid 10001 app \
    && useradd -m -g app --uid 10001 -s /usr/sbin/nologin app

COPY . /app

RUN apt-get update && \
    pip install -U pip && \
    pip install -r requirements/default.txt && \
    pip install -r checks/remotesettings/requirements.txt && \
    apt-get -q --yes autoremove && \
    apt-get clean && \
    rm -rf /root/.cache

ENV PYTHONPATH=/app
ENV HOST=0.0.0.0
ENV PORT=8000
EXPOSE 8000

# run as non priviledged user
USER app

ENTRYPOINT ["/app/scripts/run.sh"]
CMD ["server"]
