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
        print("ATTENTION: DATABASE_URL non trouvé, utilisation d'une base SQLite locale.")
        SQLALCHEMY_DATABASE_URI = "sqlite:///local.db"

    # NOUVELLE CONFIGURATION POUR L'ENVOI D'E-MAILS
    MAIL_SERVER = os.getenv('MAIL_SERVER', 'smtp.gmail.com')
    MAIL_PORT = int(os.getenv('MAIL_PORT', 587))
    MAIL_USE_TLS = os.getenv('MAIL_USE_TLS', 'true').lower() in ['true', '1', 't']
    MAIL_USERNAME = os.getenv('MAIL_USERNAME') # Votre adresse e-mail
    MAIL_PASSWORD = os.getenv('MAIL_PASSWORD') # Le mot de passe de votre e-mail (ou mot de passe d'application)