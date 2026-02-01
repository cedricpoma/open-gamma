import boto3
from botocore.config import Config

ACCESS_KEY = "d97e5f1a-39d3-40d8-ad7e-2dec84046c9b"
SECRET_KEY = "8_qZTw25w7xtkqf6CXWE0GNoI2_QjwWX"
ENDPOINT_URL = "https://files.massive.com"
BUCKET_NAME = "flatfiles"

def scan_folders():
    print(f"=== SCAN DES DOSSIERS DISPONIBLES ===")
    s3 = boto3.client(
        's3',
        aws_access_key_id=ACCESS_KEY,
        aws_secret_access_key=SECRET_KEY,
        endpoint_url=ENDPOINT_URL,
        config=Config(signature_version='s3v4')
    )
    
    # On liste 100 objets pour voir la diversité des dossiers
    response = s3.list_objects_v2(Bucket=BUCKET_NAME, MaxKeys=100)
    
    folders = set()
    if 'Contents' in response:
        for obj in response['Contents']:
            path_parts = obj['Key'].split('/')
            if len(path_parts) > 1:
                folders.add(path_parts[0])
        
        print(f"Dossiers principaux trouvés : {folders}")
        
        # On cherche spécifiquement si un dossier contient "options" ou "stocks"
        found_options = any("options" in f for f in folders)
        found_stocks = any("stocks" in f for f in folders)
        
        print(f"Options trouvées : {found_options}")
        print(f"Stocks trouvés : {found_stocks}")
    else:
        print("Aucun fichier trouvé.")

if __name__ == "__main__":
    scan_folders()
