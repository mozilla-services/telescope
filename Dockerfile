#
# Static build of `curl` with both HTTP2 and HTTP3 support.
#
# This was adapted from stunnel's script:
# https://github.com/stunnel/static-curl/blob/f8a20698bd39b6/build.sh
#
FROM alpine AS buildcurl

RUN apk update && \
    apk add \
        build-base clang automake cmake autoconf libtool linux-headers git \
        binutils cunit-dev

ENV PREFIX=/opt/curl
ENV PKG_CONFIG_PATH=$PREFIX/lib/pkgconfig:$PREFIX/lib64/pkgconfig:$PKG_CONFIG_PATH

RUN git clone --depth 1 -b openssl-3.0.8+quic https://github.com/quictls/openssl && \
    cd openssl && \
    mkdir -p "${PREFIX}/lib/" "${PREFIX}/lib64/" "${PREFIX}/include/" && \
    ./config -fPIC --prefix="${PREFIX}" \
        threads no-shared enable-tls1_3 && \
    make -j $(nproc) && \
    make install_sw && \
    cd ..

RUN git clone -b v0.11.0 https://github.com/ngtcp2/nghttp3 && \
    cd nghttp3 && \
    autoreconf -i --force && \
    PKG_CONFIG="pkg-config --static --with-path=$PREFIX/lib/pkgconfig" \
        ./configure --prefix="${PREFIX}" --enable-static --enable-shared=no --enable-lib-only && \
    make -j $(nproc) && \
    make install && \
    cd ..

RUN git clone -b v0.15.0 https://github.com/ngtcp2/ngtcp2 && \
    cd ngtcp2 && \
    autoreconf -i --force && \
    PKG_CONFIG="pkg-config --static --with-path=${PREFIX}/lib/pkgconfig:${PREFIX}/lib64/pkgconfig" \
        ./configure --prefix="${PREFIX}" --enable-static --with-openssl=${PREFIX} \
            --with-libnghttp3=${PREFIX} --enable-lib-only --enable-shared=no && \
    make -j $(nproc) check && \
    make install && \
    cd ..

RUN git clone https://github.com/nghttp2/nghttp2 && \
    cd nghttp2 && \
    autoreconf -i --force && \
    PKG_CONFIG="pkg-config --static --with-path=$PREFIX/lib/pkgconfig" \
        ./configure --prefix="${PREFIX}" --enable-static --enable-http3 \
            --enable-lib-only --enable-shared=no && \
    make -j $(nproc) check && \
    make install && \
    cd ..

RUN git clone https://github.com/curl/curl && \
    cd curl && \
    autoreconf -i --force && \
    PKG_CONFIG="pkg-config --static" \
        ./configure --prefix="${PREFIX}" \
            --disable-shared --enable-static \
             --with-openssl \
             --with-nghttp2 --with-nghttp3 --with-ngtcp2 && \
    make -j $(nproc) V=1 LDFLAGS="-L${PREFIX}/lib -L${PREFIX}/lib64 -static -all-static" CFLAGS="-O3" && \
    make install && \
    # We now have a static binary of curl at `${PREFIX}/bin/curl`
    cd ..


#
# Production container.
#
FROM python:3.11-slim-buster AS production

WORKDIR /app

RUN groupadd --gid 10001 app \
    && useradd -m -g app --uid 10001 -s /usr/sbin/nologin app

RUN apt-get update && \
    apt-get install --yes --no-install-recommends build-essential && \
    pip install --progress-bar=off -U pip && \
    pip install poetry && \
    apt-get -q --yes autoremove && \
    apt-get clean && \
    rm -rf /root/.cache

COPY --from=buildcurl /opt/curl/bin/curl /usr/local/bin/curl
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
