FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY bot.py storage.py config.py content.py ./
RUN useradd -u 10001 -m bot && mkdir /data && chown bot:bot /data
USER bot
CMD ["python", "bot.py"]
