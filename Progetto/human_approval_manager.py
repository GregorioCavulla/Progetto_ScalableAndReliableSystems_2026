#!/usr/bin/env python3

import os
import json
import time
from pathlib import Path

# Percorso al file delle approvazioni
APPROVALS_FILE = Path("data/pending_approvals.jsonl")

def load_approvals():
    """Carica tutte le richieste di approvazione dal file"""
    if not APPROVALS_FILE.exists():
        return []
    
    approvals = []
    try:
        with open(APPROVALS_FILE, "r") as f:
            for line in f:
                if line.strip():
                    approvals.append(json.loads(line.strip()))
    except Exception as e:
        print(f"Errore nel caricamento delle approvazioni: {e}")
        return []
    
    return approvals

def save_approvals(approvals):
    """Salva tutte le richieste di approvazione nel file"""
    try:
        with open(APPROVALS_FILE, "w") as f:
            for approval in approvals:
                f.write(json.dumps(approval) + "\n")
    except Exception as e:
        print(f"Errore nel salvataggio delle approvazioni: {e}")

def handle_pending_approval(approval):
    """Gestisce una singola richiesta di approvazione"""
    print("\n" + "="*60)
    print("🔔 RICHIESTA DI APPROVAZIONE UMANA")
    print("="*60)
    print(f"ID Richiesta: {approval['request_id']}")
    print(f"Tipo Azione: {approval['action_type']}")
    print(f"Motivo: {approval['reason']}")
    print(f"Dettagli: {json.dumps(approval['payload'], indent=2)}")
    print("="*60)
    
    while True:
        response = input("Vuoi APPROVARE questa richiesta? (sì/no): ").strip().lower()
        if response in ['sì', 'si', 's', 'yes', 'y']:
            approval['status'] = 'approved'
            print("✅ Richiesta APPROVATA!")
            return True
        elif response in ['no', 'n']:
            approval['status'] = 'rejected'
            print("❌ Richiesta RIFIUTATA!")
            return True
        else:
            print("Risposta non valida. Inserisci 'sì' o 'no'.")

def main():
    print("🚀 AVVIO GESTORE APPROVAZIONI UMANE")
    print("Controllo richieste ogni 10 secondi...")
    print("Premi Ctrl+C per uscire.")
    
    while True:
        try:
            approvals = load_approvals()
            pending = [a for a in approvals if a['status'] == 'pending']
            
            if pending:
                print(f"\n📋 Trovate {len(pending)} richieste pendenti")
                for approval in pending:
                    if handle_pending_approval(approval):
                        # Salva le modifiche
                        save_approvals(approvals)
                        break  # Gestisci una alla volta per non sovraccaricare l'utente
            else:
                print(".", end="", flush=True)  # Indicatore di controllo attivo
            
            time.sleep(10)  # Controlla ogni 10 secondi
            
        except KeyboardInterrupt:
            print("\n\n👋 Uscita dal gestore approvazioni.")
            break
        except Exception as e:
            print(f"\n❌ Errore: {e}")
            time.sleep(5)

if __name__ == "__main__":
    main()