import boto3
from botocore.config import Config
import os

# Informations Flat File fournies
ACCESS_KEY = "8_qZTw25w7xtkqf6CXWE0GNoI2_QjwWX"
SECRET_KEY = "d97e5f1a-39d3-40d8-ad7e-2dec84046c9b"
ENDPOINT_URL = "https://files.massive.com"
BUCKET_NAME = "flatfiles"

def test_flat_file_access():
    print(f"=== TEST ACCÈS FLAT FILE (MASSIVE/POLYGON) ===")
    
    try:
        # Configuration pour l'endpoint Massive (S3 compatible)
        s3 = boto3.client(
            's3',
            aws_access_key_id=ACCESS_KEY,
            aws_secret_access_key=SECRET_KEY,
            endpoint_url=ENDPOINT_URL,
            config=Config(signature_version='s3v4')
        )
        
        print(f"Tentative de listage des fichiers dans le bucket '{BUCKET_NAME}'...")
        
        # On essaie de lister la structure pour les options (chemin classique us_options)
        # On commence large pour voir ce qui est accessible
        response = s3.list_objects_v2(Bucket=BUCKET_NAME, MaxKeys=10)
        
        if 'Contents' in response:
            print("[OK] Connexion réussie ! Voici les premiers fichiers trouvés :")
            for obj in response['Contents']:
                print(f"- {obj['Key']} ({obj['Size'] / 1024 / 1024:.2f} MB)")
        else:
            print("[WARN] Connexion réussie, mais aucun fichier trouvé dans le bucket.")
            
    except Exception as e:
        print(f"[ERREUR] Échec de l'accès Flat File : {e}")

if __name__ == "__main__":
    # Vérifier si boto3 est installé, sinon l'installer est nécessaire
    try:
        import boto3
    except ImportError:
        print("Installation de boto3 requise...")
        os.system('pip install boto3')
        import boto3
        
    test_flat_file_access()
