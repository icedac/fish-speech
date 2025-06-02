#!/bin/bash
# Development setup script for VoiceReel with Celery/Redis

set -e

echo "=== VoiceReel Development Setup ==="

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is not installed. Please install Docker first."
    exit 1
fi

# Check if docker-compose is installed
if ! command -v docker-compose &> /dev/null; then
    echo "❌ docker-compose is not installed. Please install docker-compose first."
    exit 1
fi

# Start services
echo "🚀 Starting Redis and PostgreSQL..."
docker-compose -f docker-compose.voicereel.yml up -d redis postgres

# Wait for services to be ready
echo "⏳ Waiting for services to be ready..."
sleep 5

# Check Redis
echo "🔍 Checking Redis connection..."
docker-compose -f docker-compose.voicereel.yml exec -T redis redis-cli ping || {
    echo "❌ Redis is not responding"
    exit 1
}
echo "✅ Redis is ready"

# Check PostgreSQL
echo "🔍 Checking PostgreSQL connection..."
docker-compose -f docker-compose.voicereel.yml exec -T postgres pg_isready -U voicereel || {
    echo "❌ PostgreSQL is not responding"
    exit 1
}
echo "✅ PostgreSQL is ready"

# Install Python dependencies
echo "📦 Installing Python dependencies..."
pip install -e . || {
    echo "❌ Failed to install dependencies"
    exit 1
}

# Set environment variables
echo "🔧 Setting environment variables..."
cat > .env.voicereel << EOF
export VR_REDIS_URL="redis://localhost:6379/0"
export VR_DSN="postgresql://voicereel:voicereel_pass@localhost:5432/voicereel"
export VR_API_KEY="dev_api_key"
export VR_HMAC_SECRET="dev_hmac_secret"
EOF

echo "✅ Environment file created: .env.voicereel"

# Initialize database
echo "🗄️ Initializing database schema..."
python -c "
import os
os.environ['VR_DSN'] = 'postgresql://voicereel:voicereel_pass@localhost:5432/voicereel'
from voicereel.db import init_db
db = init_db(os.environ['VR_DSN'])
print('Database initialized successfully')
"

# Run tests
echo "🧪 Running tests..."
python -m pytest tests/test_voicereel_celery.py -v || {
    echo "⚠️ Some tests failed (this might be expected if Redis is not fully configured)"
}

echo ""
echo "=== Setup Complete! ==="
echo ""
echo "To start development:"
echo "1. Source environment variables: source .env.voicereel"
echo "2. Start Celery worker: python -m voicereel.worker"
echo "3. Start API server: python -m voicereel.flask_app"
echo "4. (Optional) Start Flower: celery -A voicereel.celery_app flower"
echo ""
echo "Services running:"
echo "- Redis: localhost:6379"
echo "- PostgreSQL: localhost:5432"
echo "- API will run on: localhost:8080"
echo "- Flower (if started): localhost:5555"