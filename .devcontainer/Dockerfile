FROM mcr.microsoft.com/devcontainers/base:ubuntu-22.04

# Installa LaTeX e scarica KIND direttamente durante la build dell'immagine
RUN apt-get update && export DEBIAN_FRONTEND=noninteractive \
    && apt-get install -y texlive-latex-extra texlive-lang-italian \
    && curl -Lo /usr/local/bin/kind https://kind.sigs.k8s.io/dl/v0.22.0/kind-linux-amd64 \
    && chmod +x /usr/local/bin/kind \
    && apt-get clean -y && rm -rf /var/lib/apt/lists/*
