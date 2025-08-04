import os
import re
import pdfplumber
import unicodedata
import io
from flask import Blueprint, render_template, request, flash, redirect, url_for, session
from flask_login import login_required, current_user, login_user, logout_user
from mistralai.client import MistralClient
from mistralai.models.chat_completion import ChatMessage
from groq import Groq
from parser import analyser_texte_bulletin
from models import db, Classe, Analyse, User, Prompt, AIProvider

main = Blueprint('main', __name__)

def get_ai_response(provider, system_prompt, user_prompt):
    """Appelle le bon fournisseur d'IA et retourne la réponse."""
    if provider.name.lower() == 'mistral':
        client = MistralClient(api_key=provider.api_key)
        messages = [ChatMessage(role="system", content=system_prompt), ChatMessage(role="user", content=user_prompt)]
        chat_response = client.chat(model=provider.model_name, messages=messages, temperature=0.6)
        return chat_response.choices[0].message.content
    elif provider.name.lower() == 'groq':
        client = Groq(api_key=provider.api_key)
        chat_completion = client.chat.completions.create(
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            model=provider.model_name, temperature=0.5
        )
        return chat_completion.choices[0].message.content
    else:
        raise ValueError(f"Fournisseur d'IA '{provider.name}' non supporté.")

@main.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: return redirect(url_for('main.accueil'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username == os.getenv('APP_USERNAME') and password == os.getenv('APP_PASSWORD'):
            user = User(id=1)
            login_user(user)
            return redirect(url_for('main.accueil'))
        else: flash('Échec de la connexion.', 'danger')
    return render_template('login.html')

@main.route('/logout')
@login_required
def logout():
    session.clear()
    logout_user()
    return redirect(url_for('main.login'))

@main.route('/', methods=['GET', 'POST'])
@login_required
def accueil():
    if request.method == 'POST':
        session['classe_id'] = request.form.get('classe_id')
        return redirect(url_for('main.analyser'))
    try:
        classes = Classe.query.order_by(Classe.annee_scolaire.desc(), Classe.nom_classe).all()
        derniere_classe_id = session.get('classe_id')
        return render_template('accueil.html', classes=classes, derniere_classe_id=derniere_classe_id)
    except Exception as e:
        flash(f"La base de données n'est pas initialisée. Veuillez visiter l'URL /init-db-manuellement. Erreur: {e}", "warning")
        return render_template('accueil.html', classes=[], derniere_classe_id=None)

@main.route('/analyser', methods=['GET', 'POST'])
@login_required
def analyser():
    classe_id = session.get('classe_id')
    if not classe_id: return redirect(url_for('main.accueil'))
    classe = Classe.query.get_or_404(classe_id)
    eleves_liste = [e.strip() for e in classe.eleves.split('\n') if e.strip()]
    matieres_attendues = [m.strip() for m in classe.matieres.split(',') if m.strip()]
    if request.method == 'POST':
        fichier = request.files.get('bulletin_pdf')
        nom_eleve = request.form.get('nom_eleve', '').strip()
        trimestre_str = request.form.get('trimestre')
        if not all([fichier, nom_eleve, trimestre_str]):
            flash("Tous les champs sont requis.", "danger")
            return redirect(url_for('main.analyser'))
        trimestre = int(trimestre_str)
        try:
            active_provider = AIProvider.query.filter_by(is_active=True).first()
            active_prompt = Prompt.query.filter_by(is_active=True).first()
            if not active_provider or not active_prompt:
                raise ValueError("Veuillez définir un Fournisseur IA et un Prompt actifs dans la Configuration.")
            
            pdf_bytes = fichier.read()
            texte_extrait = ""
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                texte_extrait = pdf.pages[0].extract_text() or ""
            if not texte_extrait: raise ValueError("Le contenu du PDF est vide.")
            
            donnees_structurees = analyser_texte_bulletin(texte_extrait, nom_eleve, matieres_attendues)
            if not donnees_structurees.get("nom_eleve"): raise ValueError(f"Le nom '{nom_eleve}' n'a pas été trouvé dans le PDF.")
            if len(donnees_structurees["appreciations_matieres"]) != len(matieres_attendues): raise ValueError("Le parser n'a pas trouvé le bon nombre de matières.")
            
            appreciations_precedentes = ""
            if trimestre > 1:
                analyses_t1 = Analyse.query.filter_by(classe_id=classe_id, nom_eleve=nom_eleve, trimestre=1).first()
                if analyses_t1: appreciations_precedentes += f"Appréciation du Trimestre 1:\n{analyses_t1.appreciation_principale}\n\n"
            if trimestre > 2:
                analyses_t2 = Analyse.query.filter_by(classe_id=classe_id, nom_eleve=nom_eleve, trimestre=2).first()
                if analyses_t2: appreciations_precedentes += f"Appréciation du Trimestre 2:\n{analyses_t2.appreciation_principale}\n\n"
            
            contexte_trimestre = "C'est le début de l'année, l'appréciation doit être encourageante et fixer des objectifs clairs pour les deux trimestres restants." if trimestre == 1 else "C'est le milieu de l'année. L'appréciation doit faire le bilan des progrès par rapport au T1 et motiver pour le dernier trimestre." if trimestre == 2 else "C'est la fin de l'année. L'appréciation doit être un bilan final, tenir compte de l'évolution sur l'année et donner des conseils pour la poursuite d'études."
            liste_appreciations = "\n".join([f"- {item['matiere']} ({item['moyenne']}): {item['commentaire']}" for item in donnees_structurees['appreciations_matieres']])
            
            prompt_systeme = active_prompt.system_message
            prompt_utilisateur = active_prompt.user_message_template.format(
                nom_eleve=nom_eleve, trimestre=trimestre, contexte_trimestre=contexte_trimestre,
                appreciations_precedentes=appreciations_precedentes, liste_appreciations=liste_appreciations
            )
            
            reponse_ia = get_ai_response(active_provider, prompt_systeme, prompt_utilisateur)
            
            separateur = "--- JUSTIFICATIONS ---"
            if separateur in reponse_ia:
                parties = reponse_ia.split(separateur, 1)
                appreciation, justifications = parties[0].strip(), parties[1].strip()
            else:
                appreciation, justifications = reponse_ia, ""
            
            analyse_existante = Analyse.query.filter_by(classe_id=classe_id, nom_eleve=nom_eleve, trimestre=trimestre).first()
            if analyse_existante:
                analyse_existante.appreciation_principale, analyse_existante.justifications, analyse_existante.donnees_brutes = appreciation, justifications, donnees_structurees
                analyse_a_afficher = analyse_existante
            else:
                nouvelle_analyse = Analyse(nom_eleve=nom_eleve, trimestre=trimestre, appreciation_principale=appreciation, justifications=justifications, donnees_brutes=donnees_structurees, classe_id=classe_id)
                db.session.add(nouvelle_analyse)
                analyse_a_afficher = nouvelle_analyse
            db.session.commit()
            return render_template('resultat.html', res=analyse_a_afficher, classe=classe)
        except Exception as e:
            flash(f"Une erreur est survenue : {e}", "danger")
            return redirect(url_for('main.analyser'))
    
    analyses_faites = {}
    for analyse in Classe.query.get(classe_id).analyses:
        if analyse.nom_eleve not in analyses_faites: analyses_faites[analyse.nom_eleve] = set()
        analyses_faites[analyse.nom_eleve].add(analyse.trimestre)
    return render_template('analyser.html', classe=classe, eleves_liste=eleves_liste, analyses_faites=analyses_faites)

@main.route('/configuration', methods=['GET', 'POST'])
@login_required
def configuration():
    if request.method == 'POST':
        annee, nom_classe, matieres, eleves = request.form.get('annee_scolaire'), request.form.get('nom_classe'), request.form.get('matieres'), request.form.get('eleves')
        if all([annee, nom_classe, matieres, eleves]):
            db.session.add(Classe(annee_scolaire=annee, nom_classe=nom_classe, matieres=matieres, eleves=eleves))
            db.session.commit()
            flash("Nouvelle classe ajoutée !", "success")
        return redirect(url_for('main.configuration'))
    classes = Classe.query.order_by(Classe.annee_scolaire.desc()).all()
    return render_template('configuration.html', classes=classes)

@main.route('/classe/supprimer/<int:classe_id>', methods=['POST'])
@login_required
def supprimer_classe(classe_id):
    classe = Classe.query.get_or_404(classe_id)
    db.session.delete(classe)
    db.session.commit()
    return redirect(url_for('main.configuration'))

@main.route('/historique/<int:classe_id>')
@login_required
def historique_classe(classe_id):
    classe = Classe.query.get_or_404(classe_id)
    analyses_par_eleve = {}
    eleves_tries = sorted(list(set(a.nom_eleve for a in classe.analyses)))
    for nom_eleve in eleves_tries:
        analyses_par_eleve[nom_eleve] = sorted([a for a in classe.analyses if a.nom_eleve == nom_eleve], key=lambda x: x.trimestre)
    return render_template('historique.html', classe=classe, analyses_par_eleve=analyses_par_eleve)

@main.route('/prompts')
@login_required
def list_prompts():
    prompts = Prompt.query.order_by(Prompt.name).all()
    return render_template('prompts.html', prompts=prompts)

@main.route('/prompts/add', methods=['GET', 'POST'])
@login_required
def add_prompt():
    if request.method == 'POST':
        name, system_message, user_message_template = request.form.get('name'), request.form.get('system_message'), request.form.get('user_message_template')
        if not all([name, system_message, user_message_template]):
            flash("Tous les champs sont requis.", "warning")
            return redirect(url_for('main.add_prompt'))
        new_prompt = Prompt(name=name, system_message=system_message, user_message_template=user_message_template)
        db.session.add(new_prompt)
        db.session.commit()
        flash(f"Prompt '{name}' ajouté !", "success")
        return redirect(url_for('main.list_prompts'))
    return render_template('prompts_form.html', prompt=None)

@main.route('/prompts/edit/<int:prompt_id>', methods=['GET', 'POST'])
@login_required
def edit_prompt(prompt_id):
    prompt = Prompt.query.get_or_404(prompt_id)
    if request.method == 'POST':
        prompt.name = request.form.get('name')
        prompt.system_message = request.form.get('system_message')
        prompt.user_message_template = request.form.get('user_message_template')
        db.session.commit()
        flash(f"Prompt '{prompt.name}' mis à jour !", "success")
        return redirect(url_for('main.list_prompts'))
    return render_template('prompts_form.html', prompt=prompt)

@main.route('/prompts/set_active/<int:prompt_id>', methods=['POST'])
@login_required
def set_active_prompt(prompt_id):
    Prompt.query.update({'is_active': False})
    prompt = Prompt.query.get_or_404(prompt_id)
    prompt.is_active = True
    db.session.commit()
    flash(f"Prompt '{prompt.name}' activé !", "success")
    return redirect(url_for('main.list_prompts'))

@main.route('/prompts/delete/<int:prompt_id>', methods=['POST'])
@login_required
def delete_prompt(prompt_id):
    prompt = Prompt.query.get_or_404(prompt_id)
    if prompt.is_active:
        flash("Impossible de supprimer un prompt actif.", "danger")
    else:
        db.session.delete(prompt)
        db.session.commit()
        flash(f"Prompt '{prompt.name}' supprimé !", "info")
    return redirect(url_for('main.list_prompts'))

@main.route('/providers')
@login_required
def list_providers():
    providers = AIProvider.query.order_by(AIProvider.name).all()
    return render_template('providers.html', providers=providers)

@main.route('/providers/add', methods=['GET', 'POST'])
@login_required
def add_provider():
    if request.method == 'POST':
        name, api_key, model_name = request.form.get('name'), request.form.get('api_key'), request.form.get('model_name')
        if not all([name, api_key, model_name]):
            flash("Tous les champs sont requis.", "warning")
        else:
            new_provider = AIProvider(name=name, api_key=api_key, model_name=model_name)
            db.session.add(new_provider)
            db.session.commit()
            flash(f"Fournisseur '{name}' ajouté !", "success")
            return redirect(url_for('main.list_providers'))
    return render_template('providers_form.html', provider=None)

@main.route('/providers/edit/<int:provider_id>', methods=['GET', 'POST'])
@login_required
def edit_provider(provider_id):
    provider = AIProvider.query.get_or_404(provider_id)
    if request.method == 'POST':
        provider.name = request.form.get('name')
        new_api_key = request.form.get('api_key')
        if new_api_key:
            provider.api_key = new_api_key
        provider.model_name = request.form.get('model_name')
        db.session.commit()
        flash(f"Fournisseur '{provider.name}' mis à jour !", "success")
        return redirect(url_for('main.list_providers'))
    return render_template('providers_form.html', provider=provider)

@main.route('/providers/set_active/<int:provider_id>', methods=['POST'])
@login_required
def set_active_provider(provider_id):
    AIProvider.query.update({'is_active': False})
    provider = AIProvider.query.get_or_404(provider_id)
    provider.is_active = True
    db.session.commit()
    flash(f"Fournisseur '{provider.name}' activé !", "success")
    return redirect(url_for('main.list_providers'))

@main.route('/providers/delete/<int:provider_id>', methods=['POST'])
@login_required
def delete_provider(provider_id):
    provider = AIProvider.query.get_or_404(provider_id)
    if provider.is_active:
        flash("Impossible de supprimer un fournisseur actif.", "danger")
    else:
        db.session.delete(provider)
        db.session.commit()
        flash(f"Fournisseur '{provider.name}' supprimé !", "info")
    return redirect(url_for('main.list_providers'))

@main.route('/init-db-manuellement')
@login_required
def init_db_manually():
    try:
        db.drop_all()
        db.create_all()
        
        if not Prompt.query.first():
            default_prompt = Prompt(
                name="Prompt par Défaut",
                system_message="Tu es un professeur principal qui rédige l'appréciation générale. Ton style est synthétique, analytique et tu justifies tes conclusions.",
                user_message_template="""Rédige une appréciation pour l'élève {nom_eleve} pour le trimestre {trimestre}.
Contexte: {contexte_trimestre}

{appreciations_precedentes}
Voici les données BRUTES du trimestre actuel :
{liste_appreciations}

Ta réponse doit être en DEUX parties, séparées par "--- JUSTIFICATIONS ---".
**Partie 1 : Appréciation Globale**
Rédige un paragraphe de 2 à 3 phrases pour le bulletin en tenant compte de l'évolution de l'élève.
**Partie 2 : Justifications**
Sous le séparateur, justifie chaque idée clé avec des citations brutes des commentaires du trimestre actuel.""",
                is_active=True
            )
            db.session.add(default_prompt)
        
        if not AIProvider.query.first():
             default_provider = AIProvider(
                name="Mistral",
                api_key=os.getenv("MISTRAL_API_KEY", "CHANGER_CETTE_CLE_DANS_LA_CONFIGURATION"),
                model_name="mistral-large-latest",
                is_active=True
             )
             db.session.add(default_provider)

        db.session.commit()
        flash("La base de données a été réinitialisée avec succès ! Un prompt et un fournisseur par défaut ont été créés.", "success")
    except Exception as e:
        flash(f"Erreur lors de l'initialisation de la BDD : {e}", "danger")
    return redirect(url_for('main.accueil'))