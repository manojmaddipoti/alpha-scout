# 1. Base Image
FROM python:3.10-slim

# 2. Prevent Python from buffering logs (CRITICAL for debugging)
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# 3. Streamlit Configuration (Prevent hangs)
ENV STREAMLIT_BROWSER_GATHER_USAGE_STATS=false
ENV STREAMLIT_SERVER_HEADLESS=true
ENV STREAMLIT_SERVER_ENABLE_CORS=false
ENV STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION=false

# 4. System Dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# 5. Set Working Directory
WORKDIR /app

# 6. Install Python Dependencies
COPY requirements.txt .
RUN pip3 install --no-cache-dir --upgrade pip && \
    pip3 install --no-cache-dir -r requirements.txt

# 7. Copy Application Code
COPY . .

# 8. Verify Critical Files Exist
RUN echo "=== Verifying Files ===" && \
    ls -la /app && \
    test -f app.py && echo "✅ app.py exists" || echo "❌ app.py MISSING" && \
    test -f search_agent.py && echo "✅ search_agent.py exists" || echo "⚠️ search_agent.py missing" && \
    test -f database.py && echo "✅ database.py exists" || echo "⚠️ database.py missing"

# 9. Create writable directory for SQLite database
RUN mkdir -p /tmp/data && chmod 777 /tmp/data

# 10. Expose Port
EXPOSE 8501

# 11. Health Check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health', timeout=5)" || exit 1

# 12. Run Streamlit (CLEAN - No shell wrapper)
CMD ["streamlit", "run", "app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false"]