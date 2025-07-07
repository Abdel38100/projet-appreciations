import os
from redis import from_url
from rq import Worker

# La liste des files d'attente que ce worker va écouter.
listen = ['default']

# On récupère l'URL de notre instance Redis.
redis_url = os.getenv('REDIS_URL', 'redis://localhost:6379')
# On établit la connexion à Redis.
conn = from_url(redis_url)

if __name__ == '__main__':
    print("Lancement du worker...")
    # On crée l'objet Worker en lui passant la liste des files et la connexion.
    # C'est la syntaxe la plus courante et la plus simple.
    # Plus besoin de 'with Connection(...)'.
    worker = Worker(listen, connection=conn)
    
    # On lance le worker.
    worker.work()