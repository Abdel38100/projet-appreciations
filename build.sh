#!/usr/bin/env bash
# exit on error
set -o errexit

# Installe les dépendances système pour WeasyPrint
apt-get update && apt-get install -y libpango-1.0-0 libpangoft2-1.0-0

# Installe les dépendances Python
pip install -r requirements.txt