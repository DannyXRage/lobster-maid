FROM python:3.12-slim
RUN pip install --no-cache-dir requests ddgs
WORKDIR /app

COPY bot.py memory.py tools_registry.py tool_calling_loop.py ./
COPY tools/ ./tools/

CMD ["python", "/app/bot.py"]

