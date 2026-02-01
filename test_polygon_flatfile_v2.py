import boto3
from botocore.config import Config

# Tentative 2 : Inversion des clés et préfixe plus spécifique
# Selon le message : Access = d97e5... et Key = 8_qZT...
ACCESS_KEY = "d97e5f1a-39d3-40d8-ad7e-2dec84046c9b"
SECRET_KEY = "8_qZTw25w7xtkqf6CXWE0GNoI2_QjwWX"
ENDPOINT_URL = "https://files.massive.com"
BUCKET_NAME = "flatfiles"

def test_flat_file_access():
    print(f"=== TEST ACCÈS FLAT FILE (ESSAI 2) ===")
    
    try:
        s3 = boto3.client(
            's3',
            aws_access_key_id=ACCESS_KEY,
            aws_secret_access_key=SECRET_KEY,
            endpoint_url=ENDPOINT_URL,
            config=Config(signature_version='s3v4')
        )
        
        # Test 1: Lister avec un préfixe commun pour les options
        prefix = "us_options_otu/"
        print(f"Tentative de listage avec préfixe '{prefix}'...")
        response = s3.list_objects_v2(Bucket=BUCKET_NAME, Prefix=prefix, MaxKeys=5)
        
        if 'Contents' in response:
            print("[OK] Succès avec préfixe !")
            for obj in response['Contents']:
                print(f"- {obj['Key']}")
        else:
            # Test 2: Lister le bucket entier si le préfixe a échoué
            print("Aucun contenu avec ce préfixe, essai sans préfixe...")
            response = s3.list_objects_v2(Bucket=BUCKET_NAME, MaxKeys=5)
            if 'Contents' in response:
                print("[OK] Succès sans préfixe !")
                for obj in response['Contents']:
                    print(f"- {obj['Key']}")
            else:
                print("[WARN] Connexion OK mais bucket vide ou inaccessible.")
                
    except Exception as e:
        print(f"[ERREUR] : {e}")

if __name__ == "__main__":
    test_flat_file_access()
