#!/bin/bash
# Dev Platform Setup Script
# Run this on the dev-platform LXC container (104)

set -e

echo "=========================================="
echo "Family Archive Dev Platform Setup"
echo "=========================================="

# Update system
echo "[1/7] Updating system packages..."
apt-get update
apt-get upgrade -y

# Install base dependencies
echo "[2/7] Installing base dependencies..."
apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    git \
    curl \
    wget \
    sudo \
    openssh-server \
    ca-certificates \
    gnupg

# Enable SSH
echo "[3/7] Configuring SSH..."
systemctl enable ssh
systemctl start ssh

# Install Node.js (for Playwright)
echo "[4/7] Installing Node.js..."
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt-get install -y nodejs

# Create dev user
echo "[5/7] Creating dev user..."
if ! id "dev" &>/dev/null; then
    useradd -m -s /bin/bash dev
    echo "dev:devuser2025" | chpasswd
    usermod -aG sudo dev
fi

# Clone the repository
echo "[6/7] Setting up project..."
cd /home/dev
if [ ! -d "family_archive" ]; then
    sudo -u dev git clone https://github.com/wardnb/family_archive.git
fi
cd family_archive/dev_platform

# Set up Python environment
echo "[7/7] Setting up Python environment..."
sudo -u dev python3 -m venv venv
sudo -u dev ./venv/bin/pip install --upgrade pip
sudo -u dev ./venv/bin/pip install -r requirements.txt

# Install Playwright browsers
echo "Installing Playwright browsers..."
sudo -u dev ./venv/bin/playwright install chromium
sudo -u dev ./venv/bin/playwright install-deps

echo "=========================================="
echo "Setup complete!"
echo ""
echo "To run the dev platform:"
echo "  cd /home/dev/family_archive/dev_platform"
echo "  source venv/bin/activate"
echo "  python orchestrator.py"
echo ""
echo "Or run a specific agent:"
echo "  python orchestrator.py --agent grandma"
echo "  python orchestrator.py --agent teen"
echo "  python orchestrator.py --agent dave"
echo "  python orchestrator.py --agent security"
echo "=========================================="
