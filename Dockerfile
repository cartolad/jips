FROM python:3.14-slim-trixie AS base
RUN apt-get update && apt-get install -y unzip
RUN pip install uv
ENV UV_LINK_MODE=copy
COPY jips jips
COPY bin bin
COPY uv.lock README.md pyproject.toml .python-version ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync
EXPOSE 1989
CMD ["uv", "run", "bin/audioserver"]
