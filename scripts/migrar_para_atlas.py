"""Migra o banco mtb_nutrition do Mongo local para o MongoDB Atlas.

Rode na sua máquina (com o Mongo local no ar):

    SOURCE_URL="mongodb://127.0.0.1:27017" \
    DEST_URL="mongodb+srv://USER:PASS@cluster0.xxxxx.mongodb.net/?retryWrites=true&w=majority" \
    ./venv/bin/python -m scripts.migrar_para_atlas

Copia todas as coleções. Idempotente: usa upsert por _id, então pode rodar de novo.
"""
import os
import sys
import certifi
from pymongo import MongoClient, ReplaceOne

DB_NAME = "mtb_nutrition"

source_url = os.environ.get("SOURCE_URL", "mongodb://127.0.0.1:27017")
dest_url = os.environ.get("DEST_URL", "")

if not dest_url:
    sys.exit("ERRO: defina DEST_URL com a connection string do Atlas.")

src = MongoClient(source_url)[DB_NAME]
dest_kwargs = {"tlsCAFile": certifi.where()} if "mongodb.net" in dest_url else {}
dst = MongoClient(dest_url, **dest_kwargs)[DB_NAME]

colecoes = src.list_collection_names()
if not colecoes:
    sys.exit(f"Nenhuma coleção em {source_url}/{DB_NAME}. Nada a migrar.")

print(f"Coleções a migrar: {colecoes}\n")
for nome in colecoes:
    docs = list(src[nome].find({}))
    if not docs:
        print(f"  {nome}: vazia, pulando")
        continue
    ops = [ReplaceOne({"_id": d["_id"]}, d, upsert=True) for d in docs]
    res = dst[nome].bulk_write(ops, ordered=False)
    print(f"  {nome}: {len(docs)} docs -> upserted={res.upserted_count} modified={res.modified_count}")

print("\nMigração concluída.")
