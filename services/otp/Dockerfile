FROM python:3.12-slim
WORKDIR /app
COPY app.py .
RUN useradd --create-home otp && mkdir -p /data && chown otp /data
USER otp
ENV OTP_DB=/data/otp.sqlite3 PORT=8000
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4)"
CMD ["python", "app.py"]
