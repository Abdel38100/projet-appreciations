import os

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'une-cle-secrete-par-defaut-pour-le-dev')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    DATABASE_URL = os.getenv('DATABASE_URL')
    if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
        SQLALCHEMY_DATABASE_URI = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    elif DATABASE_URL:
         SQLALCHEMY_DATABASE_URI = DATABASE_URL
    else:
        # Valeur par défaut pour le développement local si .env n'existe pas
        SQLALCHEMY_DATABASE_URI = "sqlite:///local.db"