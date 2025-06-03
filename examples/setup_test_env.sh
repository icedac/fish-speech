#!/bin/bash
# Setup script for VoiceReel local testing environment

echo "🚀 VoiceReel Local Testing Environment Setup"
echo "==========================================="

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to print status
print_status() {
    if [ $1 -eq 0 ]; then
        echo -e "${GREEN}✅ $2${NC}"
    else
        echo -e "${RED}❌ $2${NC}"
        exit 1
    fi
}

# Check prerequisites
echo -e "\n${YELLOW}Checking prerequisites...${NC}"

if command_exists conda; then
    print_status 0 "Conda is installed"
else
    print_status 1 "Conda is not installed. Please install Miniconda first."
fi

if command_exists docker; then
    print_status 0 "Docker is installed"
else
    echo -e "${YELLOW}⚠️  Docker is not installed (optional for manual setup)${NC}"
fi

# Create conda environment
echo -e "\n${YELLOW}Setting up conda environment...${NC}"
if conda env list | grep -q "voicereel"; then
    echo "Environment 'voicereel' already exists"
    read -p "Do you want to recreate it? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        conda env remove -n voicereel -y
        conda create -n voicereel python=3.10 -y
    fi
else
    conda create -n voicereel python=3.10 -y
fi

# Activate environment
echo -e "\n${YELLOW}Activating environment...${NC}"
eval "$(conda shell.bash hook)"
conda activate voicereel

# Install dependencies
echo -e "\n${YELLOW}Installing dependencies...${NC}"
pip install -e ".[stable]"
pip install redis celery psycopg2-binary boto3 numpy
pip install torch torchaudio transformers gradio loguru

# Download Fish-Speech models
echo -e "\n${YELLOW}Downloading Fish-Speech models...${NC}"
if [ ! -d "checkpoints/fish-speech-1.5" ]; then
    pip install -U "huggingface_hub[cli]"
    huggingface-cli download fishaudio/fish-speech-1.5 --local-dir checkpoints/fish-speech-1.5
    print_status $? "Fish-Speech models downloaded"
else
    echo "Models already downloaded in checkpoints/fish-speech-1.5"
fi

# Create test audio files
echo -e "\n${YELLOW}Creating test audio files...${NC}"
python examples/create_test_audio.py
print_status $? "Test audio files created"

# Setup services with Docker Compose
if command_exists docker; then
    echo -e "\n${YELLOW}Starting services with Docker Compose...${NC}"
    read -p "Start PostgreSQL and Redis with Docker? (Y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Nn]$ ]]; then
        docker-compose -f docker-compose.dev.yml up -d postgres redis
        print_status $? "Services started"
        
        # Wait for PostgreSQL to be ready
        echo "Waiting for PostgreSQL to be ready..."
        sleep 5
        
        # Run database migration
        echo -e "\n${YELLOW}Initializing database...${NC}"
        export VR_POSTGRES_DSN="postgresql://voicereel:voicereel@localhost:5432/voicereel"
        python tools/migrate_to_postgres.py
        print_status $? "Database initialized"
    fi
else
    echo -e "\n${YELLOW}Manual service setup required:${NC}"
    echo "1. Start PostgreSQL on port 5432"
    echo "2. Start Redis on port 6379"
    echo "3. Run: python tools/migrate_to_postgres.py"
fi

# Create startup script
echo -e "\n${YELLOW}Creating startup scripts...${NC}"

# API server script
cat > start_voicereel_server.sh << 'EOF'
#!/bin/bash
export VR_POSTGRES_DSN="postgresql://voicereel:voicereel@localhost:5432/voicereel"
export VR_REDIS_URL="redis://localhost:6379/0"
export VR_API_KEY="test-api-key-12345"
export VR_LOG_LEVEL="INFO"
export VR_DEBUG="true"

echo "🚀 Starting VoiceReel API Server..."
python -m voicereel.server_postgres
EOF
chmod +x start_voicereel_server.sh
print_status 0 "Created start_voicereel_server.sh"

# Celery worker script
cat > start_celery_worker.sh << 'EOF'
#!/bin/bash
export VR_POSTGRES_DSN="postgresql://voicereel:voicereel@localhost:5432/voicereel"
export VR_REDIS_URL="redis://localhost:6379/0"

echo "🔧 Starting Celery Worker..."
celery -A voicereel.tasks worker --loglevel=info
EOF
chmod +x start_celery_worker.sh
print_status 0 "Created start_celery_worker.sh"

# Summary
echo -e "\n${GREEN}✨ Setup completed!${NC}"
echo -e "\n${YELLOW}Next steps:${NC}"
echo "1. Start services (if not using Docker):"
echo "   - PostgreSQL on port 5432"
echo "   - Redis on port 6379"
echo ""
echo "2. In separate terminals, run:"
echo "   Terminal 1: ./start_celery_worker.sh"
echo "   Terminal 2: ./start_voicereel_server.sh"
echo ""
echo "3. Test the setup:"
echo "   python examples/test_register_speakers.py"
echo "   python examples/test_dialogue.py"
echo ""
echo "4. (Optional) Replace synthetic audio with real recordings:"
echo "   - test_audio/speaker1_male.wav"
echo "   - test_audio/speaker2_female.wav"
echo ""
echo -e "${GREEN}Happy testing! 🎉${NC}"