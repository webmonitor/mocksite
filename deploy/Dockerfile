# Deployment image: static site + admin API in one process, two listeners.
#
# Read-only root filesystem friendly: nothing is written at runtime. All paths
# that a process might want to write (HOME, tmp, bytecode caches) are either
# disabled or redirected to /tmp by the compose file.
#
# Build:
#   docker build -f deploy/Dockerfile -t mocksite:local .

FROM node:22-bookworm-slim AS web

WORKDIR /web
ENV PNPM_HOME=/usr/local/pnpm \
    PATH=/usr/local/pnpm:$PATH
RUN npm install --global pnpm@12.15.0 && npm cache clean --force

# Frozen install: the committed lockfile is the only accepted dependency set.
COPY web/package.json web/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY web/ ./
RUN pnpm build


FROM python:3.12-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Hashed dependency transaction, then the project itself without deps.
COPY requirements.txt /tmp/requirements.txt
RUN pip install --require-hashes -r /tmp/requirements.txt && rm /tmp/requirements.txt

RUN groupadd --gid 10001 mocksite \
    && useradd --uid 10001 --gid 10001 --no-create-home --shell /usr/sbin/nologin mocksite

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
# hatchling is a build-time requirement (declared in pyproject's [build-system]),
# not a runtime dependency, so it is not in requirements.txt. Pin it explicitly
# instead of relying on whatever isolation happens to fetch.
RUN pip install "hatchling>=1.27,<2" \
    && pip install --no-deps --no-build-isolation . \
    && pip uninstall -y hatchling \
    && rm -rf /app/src

# Built admin bundle. The site serves it from MOCKSITE_ADMIN_DIST.
COPY --from=web /web/dist /app/admin

ENV MOCKSITE_ADMIN_DIST=/app/admin \
    MOCKSITE_SITE_HOST=0.0.0.0 \
    MOCKSITE_ADMIN_HOST=0.0.0.0 \
    HOME=/tmp

USER 10001:10001
EXPOSE 9000 9001

ENTRYPOINT ["mocksite"]
