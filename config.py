import os

class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', 'une-cle-secrete-par-defaut-pour-le-dev')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Lecture robuste de l'URL de la base de données
    DATABASE_URL = os.getenv('DATABASE_URL')
    
    if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
        SQLALCHEMY_DATABASE_URI = DATABASE_URL.replace("postgres://", "postgresql://", 1)
    elif DATABASE_URL:
         SQLALCHEMY_DATABASE_URI = DATABASE_URL
    else:
        # Cette valeur ne sera utilisée que pour le développement local avec un .env
        # Sur Render, le programme plantera si DATABASE_URL est manquant, ce qui est bien.
        print("ATTENTION: DATABASE_URL non trouvé, utilisation d'une base SQLite locale.")
        SQLALCHEMY_DATABASE_URI = "sqlite:///local.db"