import os
import re
import pdfplumber
import unicodedata
import io
from flask import Blueprint, render_template, request, flash, redirect, url_for, session, current_app
from flask_login import login_required, current_user, login_user, logout_user
from mistralai.client import MistralClient
from mistralai.models.chat_completion import ChatMessage
from groq import Groq
from openai import OpenAI
from parser import analyser_texte_bulletin
from models import db, Classe, Analyse, User, Prompt, AIProvider
from flask import Response
from weasyprint import HTML
from extensions import mail
from flask_mail import Message

main = Blueprint('main', __name__)

def get_ai_response(provider, system_prompt, user_prompt):
    """Appelle le bon fournisseur d'IA et retourne la réponse."""
    provider_name = provider.name.lower()
    if provider_name == 'mistral':
        client = MistralClient(api_key=provider.api_key)
        messages = [ChatMessage(role="system", content=system_prompt), ChatMessage(role="user", content=user_prompt)]
        chat_response = client.chat(model=provider.model_name, messages=messages, temperature=0.6)
        return chat_response.choices[0].message.content
    elif provider_name == 'groq':
        client = Groq(api_key=provider.api_key)
        chat_completion = client.chat.completions.create(
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            model=provider.model_name, temperature=0.5
        )
        return chat_completion.choices[0].message.content
    elif provider_name == 'openai':
        client = OpenAI(api_key=provider.api_key)
        chat_completion = client.chat.completions.create(
            messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
            model=provider.model_name, temperature=0.5
        )
        return chat_completion.choices[0].message.content
    else:
        raise ValueError(f"Fournisseur d'IA '{provider.name}' non supporté.")

@main.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated: 
        return redirect(url_for('main.accueil'))
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)
            return redirect(url_for('main.accueil'))
        else: 
            flash('Échec de la connexion. Vérifiez le nom d\'utilisateur et le mot de passe.', 'danger')
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
    if not classe_id: 
        return redirect(url_for('main.accueil'))
    
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
                full_text = [page.extract_text() for page in pdf.pages if page.extract_text()]
                texte_extrait = "\n".join(full_text)

            if not texte_extrait: 
                raise ValueError("Le contenu du PDF est vide ou illisible.")

            donnees_structurees = analyser_texte_bulletin(texte_extrait, nom_eleve, matieres_attendues)
            
            # --- CORRECTION MAJEURE : Vérifier si le parser a fonctionné ---
            if not donnees_structurees.get("appreciations_matieres"):
                raise ValueError(
                    "Le parser n'a trouvé aucune matière. Vérifiez que les noms des matières dans la configuration de la classe "
                    "correspondent EXACTEMENT à ceux du PDF (y compris les abréviations, points, et espacements comme 'SC. ECONO.& SOCIALES')."
                )
            # --- FIN DE LA CORRECTION ---

            if not donnees_structurees.get("nom_eleve"): 
                raise ValueError(f"Le nom '{nom_eleve}' n'a pas été trouvé dans le PDF.")
            
            appreciations_precedentes = ""
            if trimestre > 1:
                analyses_t1 = Analyse.query.filter_by(classe_id=classe_id, nom_eleve=nom_eleve, trimestre=1).first()
                if analyses_t1: 
                    appreciations_precedentes += f"Appréciation du Trimestre 1:\n{analyses_t1.appreciation_principale}\n\n"
            if trimestre > 2:
                analyses_t2 = Analyse.query.filter_by(classe_id=classe_id, nom_eleve=nom_eleve, trimestre=2).first()
                if analyses_t2: 
                    appreciations_precedentes += f"Appréciation du Trimestre 2:\n{analyses_t2.appreciation_principale}\n\n"
            
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
                
            nouvelle_analyse = Analyse(
                nom_eleve=nom_eleve, 
                trimestre=trimestre, 
                appreciation_principale=appreciation, 
                justifications=justifications, 
                donnees_brutes=donnees_structurees, 
                classe_id=classe_id, 
                prompt_name=active_prompt.name, 
                provider_name=active_provider.name
            )
            db.session.add(nouvelle_analyse)
            db.session.commit()
            
            return render_template('resultat.html', res=nouvelle_analyse, classe=classe)

        except Exception as e:
            flash(f"Une erreur est survenue : {e}", "danger")
            return redirect(url_for('main.analyser'))

    return render_template('analyser.html', classe=classe, eleves_liste=eleves_liste)

@main.route('/configuration')
@login_required
def configuration():
    """Affiche uniquement la liste des classes existantes."""
    classes = Classe.query.order_by(Classe.annee_scolaire.desc()).all()
    return render_template('configuration.html', classes=classes)

@main.route('/classe/add', methods=['GET', 'POST'])
@login_required
def add_classe():
    """Gère l'ajout d'une nouvelle classe via un formulaire dédié."""
    if request.method == 'POST':
        annee = request.form.get('annee_scolaire')
        nom_classe = request.form.get('nom_classe')
        matieres = request.form.get('matieres')
        eleves = request.form.get('eleves')
        
        if all([annee, nom_classe, matieres, eleves]):
            new_classe = Classe(annee_scolaire=annee, nom_classe=nom_classe, matieres=matieres, eleves=eleves)
            db.session.add(new_classe)
            db.session.commit()
            flash("Nouvelle classe ajoutée avec succès !", "success")
            return redirect(url_for('main.configuration'))
        else:
            flash("Tous les champs sont requis.", "danger")
            
    return render_template('classe_form.html', classe=None)

@main.route('/classe/edit/<int:classe_id>', methods=['GET', 'POST'])
@login_required
def edit_classe(classe_id):
    """Gère la modification d'une classe existante."""
    classe = Classe.query.get_or_404(classe_id)
    if request.method == 'POST':
        # On met à jour uniquement les champs modifiables
        classe.matieres = request.form.get('matieres')
        classe.eleves = request.form.get('eleves')
        db.session.commit()
        flash(f"La classe '{classe.nom_classe}' a été mise à jour avec succès.", "success")
        return redirect(url_for('main.configuration'))
        
    return render_template('classe_form.html', classe=classe)

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
    
    # Logique existante pour trier par élève
    eleves_tries = sorted(list(set(a.nom_eleve for a in classe.analyses)))
    for nom_eleve in eleves_tries:
        analyses_par_eleve[nom_eleve] = sorted([a for a in classe.analyses if a.nom_eleve == nom_eleve], key=lambda x: (x.trimestre, x.created_at))
    
    # NOUVELLE LOGIQUE : Trouver les trimestres pour lesquels il existe au moins une analyse
    trimestres_disponibles = sorted(list(set(a.trimestre for a in classe.analyses)))
    
    return render_template(
        'historique.html', 
        classe=classe, 
        analyses_par_eleve=analyses_par_eleve,
        trimestres_disponibles=trimestres_disponibles  # On passe la nouvelle variable
    )

@main.route('/historique')
@login_required
def historique_global():
    """Affiche la liste de toutes les classes ayant au moins une analyse."""
    # On récupère uniquement les classes qui ont des analyses associées
    # pour ne pas afficher de classes vides sur cette page.
    classes_avec_analyses = Classe.query.filter(Classe.analyses.any()).order_by(
        Classe.annee_scolaire.desc(), Classe.nom_classe
    ).all()
    
    return render_template('historique_global.html', classes=classes_avec_analyses)

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
    
@main.route('/analyse/supprimer/<int:analyse_id>', methods=['POST'])
@login_required
def supprimer_analyse(analyse_id):
    analyse = Analyse.query.get_or_404(analyse_id)
    classe_id = analyse.classe_id
    db.session.delete(analyse)
    db.session.commit()
    return redirect(url_for('main.historique_classe', classe_id=classe_id))


@main.route('/analyse/pdf/<int:analyse_id>')
@login_required
def download_pdf(analyse_id):
    """Génère et télécharge une analyse en format PDF."""
    analyse = Analyse.query.get_or_404(analyse_id)
    classe = analyse.classe # SQLAlchemy backref nous donne accès à la classe
    
    # Rendre le template HTML avec les données de l'analyse
    html_string = render_template('pdf_template.html', analyse=analyse, classe=classe)
    
    # Utiliser WeasyPrint pour convertir le HTML en PDF
    pdf_bytes = HTML(string=html_string).write_pdf()
    
    # Créer un nom de fichier propre
    filename = f"appreciation_{analyse.nom_eleve.replace(' ', '_')}_T{analyse.trimestre}.pdf"
    
    # Renvoyer la réponse Flask avec le PDF
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-disposition": f"attachment; filename={filename}"}
    )


@main.route('/historique/pdf_classe/<int:classe_id>/trimestre/<int:trimestre>')
@login_required
def download_bulk_pdf(classe_id, trimestre):
    """
    Génère un PDF unique avec l'appréciation la plus récente de chaque élève 
    pour un trimestre donné.
    """
    classe = Classe.query.get_or_404(classe_id)
    
    # 1. Récupérer toutes les analyses pour le trimestre
    analyses_trimestre = Analyse.query.filter_by(classe_id=classe_id, trimestre=trimestre).all()
    
    # 2. Identifier tous les élèves uniques ayant une analyse
    noms_eleves = sorted(list(set(a.nom_eleve for a in analyses_trimestre)))
    
    # 3. Pour chaque élève, trouver son analyse la plus récente pour ce trimestre
    analyses_finales = []
    for nom in noms_eleves:
        analyse_recente = Analyse.query.filter_by(
            classe_id=classe_id, 
            trimestre=trimestre, 
            nom_eleve=nom
        ).order_by(Analyse.created_at.desc()).first()
        if analyse_recente:
            analyses_finales.append(analyse_recente)
    
    if not analyses_finales:
        flash(f"Aucune analyse à inclure dans le PDF pour le Trimestre {trimestre}.", "warning")
        return redirect(url_for('main.historique_classe', classe_id=classe_id))

    # 4. Rendre le template HTML avec la liste des analyses finales
    html_string = render_template('pdf_bulk_template.html', analyses=analyses_finales, classe=classe, trimestre=trimestre)
    
    # 5. Convertir en PDF
    pdf_bytes = HTML(string=html_string).write_pdf()
    
    filename = f"appreciations_{classe.nom_classe.replace(' ', '_')}_T{trimestre}.pdf"
    
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={"Content-disposition": f"attachment; filename={filename}"}
    )

@main.route('/analyse/edit/<int:analyse_id>', methods=['POST'])
@login_required
def edit_analyse(analyse_id):
    """Met à jour l'appréciation d'une analyse existante."""
    analyse = Analyse.query.get_or_404(analyse_id)
    
    nouvelle_appreciation = request.form.get('appreciation_principale')
    
    if nouvelle_appreciation:
        analyse.appreciation_principale = nouvelle_appreciation
        db.session.commit()
        flash("L'appréciation a été mise à jour avec succès.", "success")
    else:
        flash("Le champ de l'appréciation ne peut pas être vide.", "warning")

    return redirect(url_for('main.historique_classe', classe_id=analyse.classe_id))



def send_reset_email(user):
    token = user.get_reset_token()
    msg = Message('Demande de réinitialisation de mot de passe',
                  sender=current_app.config['MAIL_USERNAME'],
                  recipients=[user.email])
    msg.body = f'''Pour réinitialiser votre mot de passe, visitez le lien suivant :
{url_for('main.reset_password', token=token, _external=True)}

Si vous n'êtes pas à l'origine de cette demande, veuillez ignorer cet e-mail.
'''
    mail.send(msg)

@main.route("/account", methods=['GET', 'POST'])
@login_required
def account():
    if request.method == 'POST':
        current_user.username = request.form['username']
        current_user.email = request.form['email']
        
        password = request.form.get('password')
        password_confirm = request.form.get('password_confirm')
        
        if password:
            if password == password_confirm:
                current_user.set_password(password)
                flash('Votre mot de passe a été mis à jour !', 'success')
            else:
                flash('Les mots de passe ne correspondent pas.', 'danger')
                return render_template('account.html')
        
        db.session.commit()
        flash('Votre compte a été mis à jour !', 'success')
        return redirect(url_for('main.account'))
    
    return render_template('account.html')

@main.route("/reset_password", methods=['GET', 'POST'])
def reset_password_request():
    if current_user.is_authenticated:
        return redirect(url_for('main.accueil'))
    if request.method == 'POST':
        user = User.query.filter_by(email=request.form['email']).first()
        if user:
            send_reset_email(user)
        flash('Si un compte avec cet e-mail existe, un lien de réinitialisation a été envoyé.', 'info')
        return redirect(url_for('main.login'))
    return render_template('reset_request.html')

@main.route("/reset_password/<token>", methods=['GET', 'POST'])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for('main.accueil'))
    user = User.verify_reset_token(token)
    if user is None:
        flash('Le jeton de réinitialisation est invalide ou a expiré.', 'warning')
        return redirect(url_for('main.reset_password_request'))
    
    if request.method == 'POST':
        password = request.form.get('password')
        password_confirm = request.form.get('password_confirm')
        if password == password_confirm:
            user.set_password(password)
            db.session.commit()
            flash('Votre mot de passe a été mis à jour ! Vous pouvez vous connecter.', 'success')
            return redirect(url_for('main.login'))
        else:
            flash('Les mots de passe ne correspondent pas.', 'danger')
    return render_template('reset_token.html', token=token)

@main.route('/init-db-manuellement')
def init_db_manually():
    """
    Route web pour réinitialiser la base de données manuellement sur Render.
    ATTENTION : CECI SUPPRIME TOUTES LES DONNÉES EXISTANTES !
    """
    try:
        from models import User, Prompt, AIProvider
        from extensions import db
        from flask import current_app
        import os 

        with current_app.app_context():
            db.drop_all() 
            db.create_all()

            if not User.query.first():
                admin_username = os.getenv('APP_USERNAME', 'admin')
                admin_email = os.getenv('APP_EMAIL', 'admin@example.com')
                admin_password = os.getenv('APP_PASSWORD', 'password')
                
                admin_user = User(username=admin_username, email=admin_email)
                admin_user.set_password(admin_password)
                db.session.add(admin_user)
            
            if not Prompt.query.first():
                default_prompt = Prompt(
                    name="Prompt par Défaut",
                    system_message="Tu es un professeur principal...",
                    user_message_template="""Rédige une appréciation...""",
                    is_active=True
                )
                db.session.add(default_prompt)

            if not AIProvider.query.first():
                default_provider = AIProvider(
                    name="Mistral",
                    api_key=os.getenv("MISTRAL_API_KEY", "CHANGER_CETTE_CLE"),
                    model_name="mistral-large-latest",
                    is_active=True
                )
                db.session.add(default_provider)

            db.session.commit()

        flash("La base de données a été réinitialisée avec succès ! Vous pouvez maintenant vous connecter avec les identifiants par défaut.", "success")
    except Exception as e:
        # Maintenant, si une autre erreur survient, elle sera affichée !
        flash(f"Erreur lors de l'initialisation de la BDD : {e}", "danger")
    
    return redirect(url_for('main.login')) # Redirige vers la page de login après initialisation