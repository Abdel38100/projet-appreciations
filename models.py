from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, func, ForeignKey
from itsdangerous import URLSafeTimedSerializer as Serializer
from flask import current_app
from app import bcrypt # On importe bcrypt depuis app.py

db = SQLAlchemy()

# Le modèle User devient une table complète dans la BDD
class User(db.Model, UserMixin):
    id = Column(Integer, primary_key=True)
    username = Column(String(20), unique=True, nullable=False)
    email = Column(String(120), unique=True, nullable=False)
    password_hash = Column(String(60), nullable=False)

    def set_password(self, password):
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password):
        return bcrypt.check_password_hash(self.password_hash, password)

    def get_reset_token(self, expires_sec=1800):
        s = Serializer(current_app.config['SECRET_KEY'])
        return s.dumps({'user_id': self.id})

    @staticmethod
    def verify_reset_token(token, expires_sec=1800):
        s = Serializer(current_app.config['SECRET_KEY'])
        try:
            user_id = s.loads(token, max_age=expires_sec)['user_id']
        except:
            return None
        return User.query.get(user_id)

# Le reste des modèles ne change pas
class Classe(db.Model):
    id = db.Column(Integer, primary_key=True)
    annee_scolaire = db.Column(String(10), nullable=False)
    nom_classe = db.Column(String(50), nullable=False)
    matieres = db.Column(Text, nullable=False)
    eleves = db.Column(Text, nullable=False)
    analyses = db.relationship('Analyse', backref='classe', lazy=True, cascade="all, delete-orphan")

class Analyse(db.Model):
    id = Column(Integer, primary_key=True)
    nom_eleve = Column(String(200), nullable=False)
    trimestre = Column(Integer, nullable=False)
    appreciation_principale = Column(Text)
    justifications = Column(Text)
    donnees_brutes = Column(db.JSON)
    classe_id = Column(Integer, ForeignKey('classe.id'), nullable=False)
    prompt_name = Column(String(100))
    provider_name = Column(String(50))
    created_at = Column(DateTime, server_default=func.now())

class Prompt(db.Model):
    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True, nullable=False)
    system_message = Column(Text, nullable=False)
    user_message_template = Column(Text, nullable=False)
    is_active = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, server_default=func.now())

class AIProvider(db.Model):
    id = Column(Integer, primary_key=True)
    name = Column(String(50), unique=True, nullable=False)
    api_key = Column(String(200), nullable=False)
    model_name = Column(String(100), nullable=False)
    is_active = Column(Boolean, default=False, nullable=False)