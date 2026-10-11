# Headed Chromium under Xvfb + x11vnc + noVNC (websockify).
# Multi-arch (amd64/arm64) — works on Oracle Cloud Ampere ARM instances.
FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
      xvfb \
      x11vnc \
      websockify \
      novnc \
      openbox \
      chromium \
      fonts-liberation \
      fonts-dejavu-core \
      tzdata \
      ca-certificates \
      curl \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /profile

COPY start.sh /start.sh
RUN chmod +x /start.sh

EXPOSE 9222 6080

HEALTHCHECK --interval=15s --timeout=5s --start-period=60s --retries=5 \
  CMD curl -fsS http://127.0.0.1:9222/json/version || exit 1

ENTRYPOINT ["/start.sh"]
