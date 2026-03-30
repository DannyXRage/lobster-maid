FROM python:3.12-slim

# Chromium 运行时系统依赖 + 中日韩字体（截图/PDF 需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libdbus-1-3 libxkbcommon0 \
    libatspi2.0-0 libxcomposite1 libxdamage1 libxfixes3 \
    libxrandr2 libgbm1 libpango-1.0-0 libcairo2 libasound2 \
    fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir requests ddgs beautifulsoup4 lxml playwright \
    && playwright install chromium

WORKDIR /app
COPY bot.py memory.py tools_registry.py tool_calling_loop.py ./
COPY tools/ ./tools/
CMD ["python", "bot.py"]
