"""Cree les buckets MinIO attendus par les DAGs, puis se termine.

Execute une seule fois au demarrage de la stack (service minio-init).
Idempotent : relancer le script sur une stack deja initialisee ne change rien.
MinIO met quelques secondes a accepter les connexions, d'ou la boucle de retry.
"""

import os
import sys
import time

from minio import Minio
from minio.error import S3Error

ENDPOINT = os.getenv("MINIO_ENDPOINT", "minio:9000")
ACCESS_KEY = os.environ["MINIO_ACCESS_KEY"]
SECRET_KEY = os.environ["MINIO_SECRET_KEY"]
BUCKETS = [b.strip() for b in os.getenv("MINIO_BUCKETS", "raw").split(",") if b.strip()]
MAX_WAIT_SECONDS = int(os.getenv("MINIO_INIT_TIMEOUT", "60"))


def wait_for_minio(client) -> None:
    deadline = time.monotonic() + MAX_WAIT_SECONDS
    last_error = None
    while time.monotonic() < deadline:
        try:
            client.list_buckets()
            return
        except Exception as exc:  # reseau pas encore pret, MinIO en cours de demarrage
            last_error = exc
            time.sleep(2)
    raise TimeoutError(
        f"MinIO n'a pas repondu sur {ENDPOINT} en {MAX_WAIT_SECONDS}s : {last_error}"
    )


def main() -> int:
    client = Minio(ENDPOINT, access_key=ACCESS_KEY, secret_key=SECRET_KEY, secure=False)

    print(f"Attente de MinIO sur {ENDPOINT}...", flush=True)
    wait_for_minio(client)
    print("MinIO repond.", flush=True)

    for bucket in BUCKETS:
        try:
            if client.bucket_exists(bucket):
                print(f"  bucket '{bucket}' deja present", flush=True)
            else:
                client.make_bucket(bucket)
                print(f"  bucket '{bucket}' cree", flush=True)
        except S3Error as exc:
            print(f"  echec sur '{bucket}' : {exc}", file=sys.stderr, flush=True)
            return 1

    print("Buckets disponibles : " + ", ".join(b.name for b in client.list_buckets()), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
