import os
import re
import pdfplumber
import unicodedata
from flask import Flask, render_template, request, redirect, url_for, jsonify, flash
from flask_misaka import markdown as MisakaMarkdown
import redis
from rq import Queue
from tasks import traiter_un_bulletin
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.dialects.postgresql import JSONB
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_bcrypt import Bcrypt

# 1. On initialise les extensions SANS les lier à une app pour l'instant
db = SQLAlchemy()
bcrypt = Bcrypt()
login_manager = LoginManager()
login_manager.login_view = 'main.login' # On préfixe avec le nom du blueprint
login_manager.login_message = "Veuillez vous connecter pour accéder à cette page."
login_manager.login_message_category = "info"

# 2. On définit nos modèles de base de données
class Analyse(db.Model):
    id = db.Column(db.String(36), primary_key=True)
    nom_eleve = db.Column(db.String(200), nullable=False)
    moyenne_generale = db.Column(db.String(10))
    appreciation_principale = db.Column(db.Text, nullable=False)
    justifications = db.Column(db.Text)
    donnees_brutes = db.Column(JSONB)
    cree_le = db.Column(db.DateTime, server_default=db.func.now())

class User(UserMixin):
    def __init__(self, id):
        self.id = id

@login_manager.user_loader
def load_user(user_id):
    # Comme on n'a qu'un utilisateur, on le recrée simplement.
    return User(user_id)

# 3. On importe et on crée nos routes dans un fichier séparé pour la clarté
# (Nous allons créer ce fichier 'main.py' juste après)
from main import main as main_blueprint

# 4. On crée la "Factory" de l'application
def create_app():
    app = Flask(__name__)

    # Configuration
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'une-cle-secrete-tres-securisee')
    db_url = os.getenv('DATABASE_URL')
    if db_url and db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = db_url
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    
    UPLOAD_FOLDER = 'uploads'
    if not os.path.exists(UPLOAD_FOLDER):
        os.makedirs(UPLOAD_FOLDER)
    app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

    # On lie les extensions à notre application
    db.init_app(app)
    bcrypt.init_app(app)
    login_manager.init_app(app)

    # On enregistre le "blueprint" qui contient toutes nos routes
    app.register_blueprint(main_blueprint)

    with app.app_context():
        # S'assure que les tables sont créées si elles n'existent pas
        db.create_all()

    return app

# Gunicorn et Railway appellent cet objet 'app'
app = create_app()