# Renderer image: Python CLI + Playwright Chromium + Pandoc + docker CLI (to start the Writerside builder
# as a sibling container through the mounted Docker socket).
# The Playwright base image tag MUST match the pinned playwright version in pyproject.toml.
FROM mcr.microsoft.com/playwright/python:v1.63.0-noble

ARG PANDOC_VERSION=3.9.0.2
ARG TARGETARCH
ADD https://github.com/jgm/pandoc/releases/download/${PANDOC_VERSION}/pandoc-${PANDOC_VERSION}-1-${TARGETARCH}.deb /tmp/pandoc.deb
RUN dpkg -i /tmp/pandoc.deb && rm /tmp/pandoc.deb

COPY --from=docker:27-cli /usr/local/bin/docker /usr/local/bin/docker

WORKDIR /opt/nxo-export
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir . && nxo-export --version

WORKDIR /workspace
ENTRYPOINT ["nxo-export"]
CMD ["--help"]
