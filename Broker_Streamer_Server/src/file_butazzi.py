import subprocess
import os
import shutil


def interpella_ai(prompt):
    """Invia un prompt ad `aichat` e restituisce la risposta.
    Cerca l'eseguibile nel PATH oppure usa `AICHAT_PATH`.
    """
    path = os.getenv("AICHAT_PATH", "aichat")
    # Se non è nel PATH e non è un percorso assoluto valido, segnala errore
    if path == "aichat" and not shutil.which("aichat"):
        return "Errore: 'aichat' non è installato né AICHAT_PATH è impostato."

    try:
        risultato = subprocess.run(
            [path, "--execute"],
            input=prompt,
            capture_output=True,
            text=True,
            check=True
        )
        return risultato.stdout.strip()
    except subprocess.CalledProcessError as e:
        return f"Errore nell'esecuzione di aichat: {e.stderr}"
    except FileNotFoundError:
        return "Errore: aichat non è installato o il percorso fornito in AICHAT_PATH è errato."

def main():

    stats_disco = subprocess.check_output(["df", "-h", "/"]).decode("utf-8")

    prompt = f"""
    Analizza i seguenti dati sull'uso del disco del mio sistema Linux:
    {stats_disco}
    
    Dimmi brevemente in una riga quanta percentuale è occupata e se secondo te 
    dovrei preoccuparmi o se ho ancora abbastanza spazio.
    """

    print("--- Analisi in corso ---")
    risposta = interpella_ai(prompt)

    print(f"Risultato dall'IA:\n{risposta}")


if __name__ == "__main__":
    main()