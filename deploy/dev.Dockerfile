# Trusted development toolchain. Not the deployment image (stage 5).
# Python 3.12 and Node 22 live here so nothing is installed on the host.
FROM node:22-bookworm-slim AS node
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PNPM_HOME=/usr/local/pnpm \
    PATH=/usr/local/pnpm:$PATH

COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -s ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
    && npm install --global pnpm@12.15.0 \
    && npm cache clean --force \
    && rm -rf /usr/local/lib/node_modules/npm/docs

# Hashed dependency transaction, separate from the project install.
COPY requirements.txt ./
RUN pip install --no-cache-dir --require-hashes -r requirements.txt

RUN groupadd --gid 10001 mocksite \
    && useradd --uid 10001 --gid 10001 --create-home mocksite

WORKDIR /workspace
COPY pyproject.toml README.md LICENSE ./
COPY src ./src
# pyproject's wheel force-include pulls assets from web/targets, and hatchling
# resolves those paths even for an editable install (metadata generation). They
# only have to exist at build time; at runtime ./ is mounted over /workspace and
# the repo's own copy wins.
COPY web/targets ./web/targets
RUN pip install --no-cache-dir --no-deps -e . \
    && rm -rf /workspace/requirements.txt

USER mocksite

CMD ["python"]
