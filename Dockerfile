FROM python:3.15-slim

ARG USER=appuser
ARG GROUP=appuser

WORKDIR /app

# The image has no git, so the version comes from the build: make build-docker passes it
ARG VERSION=0.0.0
ENV SETUPTOOLS_SCM_PRETEND_VERSION_FOR_MOTHERSAUCE=$VERSION

# Add a user without root rights
RUN useradd -rms /bin/bash $USER && usermod -aG users $GROUP
RUN chown -R $USER:$GROUP /app

ENV PATH="/home/${USER}/.local/bin:${PATH}"

USER $USER

COPY --chown=$USER:$GROUP src src
COPY --chown=$USER:$GROUP pyproject.toml README.md LICENSE ./
RUN python3 -m pip install .
CMD ["mothersauce"]
