FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 HOST=0.0.0.0
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY server.py startpage.html ./
EXPOSE 8787
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8787/stats', timeout=3)"
CMD ["python", "server.py"]
