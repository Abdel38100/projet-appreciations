from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, func

db = SQLAlchemy()

class User(UserMixin):
    def __init__(self, id): self.id = id

class Classe(db.Model):
    id = db.Column(Integer, primary_key=True)
    annee_scolaire = db.Column(String(10), nullable=False)
    nom_classe = db.Column(String(50), nullable=False)
    matieres = db.Column(Text, nullable=False)
    eleves = db.Column(Text, nullable=False)
    analyses = db.relationship('Analyse', backref='classe', lazy=True, cascade="all, delete-orphan")

class Analyse(db.Model):
    id = db.Column(Integer, primary_key=True)
    nom_eleve = db.Column(String(200), nullable=False)
    trimestre = db.Column(Integer, nullable=False)
    appreciation_principale = db.Column(Text)
    justifications = db.Column(Text)
    donnees_brutes = db.Column(db.JSON)
    classe_id = db.Column(Integer, db.ForeignKey('classe.id'), nullable=False)
    # NOUVEAUX CHAMPS POUR LE SUIVI
    prompt_name = db.Column(String(100))
    provider_name = db.Column(String(50))
    created_at = db.Column(DateTime, server_default=func.now()) # Pour un tri chronologique

class Prompt(db.Model):
    id = db.Column(Integer, primary_key=True)
    name = db.Column(String(100), unique=True, nullable=False)
    system_message = db.Column(Text, nullable=False)
    user_message_template = db.Column(Text, nullable=False)
    is_active = db.Column(Boolean, default=False, nullable=False)

class AIProvider(db.Model):
    id = db.Column(Integer, primary_key=True)
    name = db.Column(String(50), unique=True, nullable=False)
    api_key = db.Column(String(200), nullable=False)
    model_name = db.Column(String(100), nullable=False)
    is_active = db.Column(Boolean, default=False, nullable=False)